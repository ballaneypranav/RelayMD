from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from infisical_client import ClientSettings, InfisicalClient
from infisical_client.schemas import GetSecretOptions
from pydantic import BaseModel

INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "production"
INFISICAL_SECRET_PATH = "/RelayMD"
TAILSCALE_SOCKET = "/tmp/tailscaled.sock"
TAILSCALE_STATE_DIR = "/tmp/tailscale-state"


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
        client = InfisicalClient(
            settings=ClientSettings(
                client_id=client_id,
                client_secret=client_secret,
                site_url=INFISICAL_BASE_URL,
            )
        )

        def get(name: str) -> str:
            return client.getSecret(
                GetSecretOptions(
                    secret_name=name,
                    project_id=INFISICAL_WORKSPACE_ID,
                    environment=INFISICAL_ENVIRONMENT,
                    path=INFISICAL_SECRET_PATH,
                )
            ).secret_value

        config = WorkerConfig(
            b2_application_key_id=get("B2_APPLICATION_KEY_ID"),
            b2_application_key=get("B2_APPLICATION_KEY"),
            b2_endpoint=get("B2_ENDPOINT"),
            bucket_name=get("BUCKET_NAME"),
            tailscale_auth_key=get("TAILSCALE_AUTH_KEY"),
            relaymd_api_token=get("RELAYMD_API_TOKEN"),
            relaymd_orchestrator_url=get("RELAYMD_ORCHESTRATOR_URL"),
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to bootstrap worker from Infisical") from exc

    hostname = os.getenv("HOSTNAME", "relaymd-worker")
    join_tailnet(config.tailscale_auth_key, hostname)
    return config
