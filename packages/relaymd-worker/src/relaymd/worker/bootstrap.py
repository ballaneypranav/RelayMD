from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
from pydantic import BaseModel

INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "production"
INFISICAL_SECRET_PATH = "/RelayMD"
TAILSCALE_SOCKET = "/tmp/tailscaled.sock"
TAILSCALE_STATE_DIR = "/tmp/tailscale-state"
REQUEST_TIMEOUT_SECONDS = 30.0


class WorkerConfig(BaseModel):
    b2_application_key_id: str
    b2_application_key: str
    b2_endpoint: str
    bucket_name: str
    tailscale_auth_key: str
    relaymd_api_token: str
    relaymd_orchestrator_url: str


def _parse_infisical_machine_token(raw_token: str | None) -> tuple[str, str]:
    if not raw_token:
        raise RuntimeError(
            "INFISICAL_TOKEN is required and must be in the format "
            "<client_id>:<client_secret>"
        )

    if ":" not in raw_token:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected format "
            "<client_id>:<client_secret>"
        )

    client_id, client_secret = raw_token.split(":", 1)
    if not client_id or not client_secret:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected non-empty "
            "<client_id>:<client_secret>"
        )
    return client_id, client_secret


def _fetch_secret(client: httpx.Client, access_token: str, secret_name: str) -> str:
    response = client.get(
        f"{INFISICAL_BASE_URL}/api/v3/secrets/raw/{secret_name}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "workspaceId": INFISICAL_WORKSPACE_ID,
            "environment": INFISICAL_ENVIRONMENT,
            "secretPath": INFISICAL_SECRET_PATH,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Failed to fetch Infisical secret: {secret_name}") from exc

    return response.json()["secret"]["secretValue"]


def join_tailnet(auth_key: str, hostname: str) -> None:
    Path(TAILSCALE_STATE_DIR).mkdir(parents=True, exist_ok=True)

    tailscaled_process = subprocess.Popen(  # noqa: S603
        [
            "tailscaled",
            "--tun=userspace-networking",
            f"--statedir={TAILSCALE_STATE_DIR}",
            f"--socket={TAILSCALE_SOCKET}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(0.2)
    exit_code = tailscaled_process.poll()
    if exit_code is not None and exit_code != 0:
        raise RuntimeError(f"tailscaled failed to start (exit code {exit_code})")

    tailscale_up = subprocess.run(  # noqa: S603
        [
            "tailscale",
            f"--socket={TAILSCALE_SOCKET}",
            "up",
            f"--authkey={auth_key}",
            f"--hostname={hostname}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if tailscale_up.returncode != 0:
        raise RuntimeError(
            "tailscale up failed with exit code "
            f"{tailscale_up.returncode}: {tailscale_up.stderr.strip()}"
        )


def run_bootstrap() -> WorkerConfig:
    machine_token = os.getenv("INFISICAL_TOKEN")
    client_id, client_secret = _parse_infisical_machine_token(machine_token)

    try:
        with httpx.Client() as client:
            login_response = client.post(
                f"{INFISICAL_BASE_URL}/api/v1/auth/universal-auth/login",
                json={"clientId": client_id, "clientSecret": client_secret},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            login_response.raise_for_status()
            access_token = login_response.json()["accessToken"]

            config = WorkerConfig(
                b2_application_key_id=_fetch_secret(client, access_token, "B2_APPLICATION_KEY_ID"),
                b2_application_key=_fetch_secret(client, access_token, "B2_APPLICATION_KEY"),
                b2_endpoint=_fetch_secret(client, access_token, "B2_ENDPOINT"),
                bucket_name=_fetch_secret(client, access_token, "BUCKET_NAME"),
                tailscale_auth_key=_fetch_secret(client, access_token, "TAILSCALE_AUTH_KEY"),
                relaymd_api_token=_fetch_secret(client, access_token, "RELAYMD_API_TOKEN"),
                relaymd_orchestrator_url=_fetch_secret(
                    client, access_token, "RELAYMD_ORCHESTRATOR_URL"
                ),
            )
    except httpx.HTTPError as exc:
        raise RuntimeError("Failed to bootstrap worker from Infisical") from exc

    hostname = os.getenv("HOSTNAME", "relaymd-worker")
    join_tailnet(config.tailscale_auth_key, hostname)
    return config
