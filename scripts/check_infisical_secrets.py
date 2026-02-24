#!/usr/bin/env python3
"""Validate required Infisical secrets are accessible via machine identity auth."""

from __future__ import annotations

import os
import sys

import httpx

INFISICAL_BASE_URL = os.environ.get("INFISICAL_BASE_URL", "https://app.infisical.com")
INFISICAL_ENVIRONMENT = os.environ.get("INFISICAL_ENVIRONMENT", "production")
INFISICAL_SECRET_PATH = os.environ.get("INFISICAL_SECRET_PATH", "/RelayMD")
REQUEST_TIMEOUT = float(os.environ.get("INFISICAL_TIMEOUT_SECONDS", "30"))

EXPECTED_SECRETS = [
    "B2_APPLICATION_KEY",
    "B2_APPLICATION_KEY_ID",
    "B2_APPLICATION_KEY_NAME",
    "B2_ENDPOINT",
    "BUCKET_NAME",
    "RELAYMD_API_TOKEN",
    "RELAYMD_ORCHESTRATOR_URL",
    "TAILSCALE_AUTH_KEY",
]


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(1)
    return value


def main() -> int:
    client_id = get_required_env("INFISICAL_CLIENT_ID")
    client_secret = get_required_env("INFISICAL_CLIENT_SECRET")
    project_id = os.environ.get("INFISICAL_PROJECT_ID", "dcf29082-7972-4bca-be58-363f6ad969c0")

    auth_resp = httpx.post(
        f"{INFISICAL_BASE_URL}/api/v1/auth/universal-auth/login",
        json={"clientId": client_id, "clientSecret": client_secret},
        timeout=REQUEST_TIMEOUT,
    )
    try:
        auth_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(
            "Infisical auth failed. Check INFISICAL_CLIENT_ID and "
            "INFISICAL_CLIENT_SECRET for a valid Universal Auth machine identity.",
            file=sys.stderr,
        )
        print(f"Status: {auth_resp.status_code}", file=sys.stderr)
        print(f"Body: {auth_resp.text}", file=sys.stderr)
        raise SystemExit(1) from exc
    access_token = auth_resp.json()["accessToken"]

    headers = {"Authorization": f"Bearer {access_token}"}
    for name in EXPECTED_SECRETS:
        resp = httpx.get(
            f"{INFISICAL_BASE_URL}/api/v3/secrets/raw/{name}",
            headers=headers,
            params={
                "workspaceId": project_id,
                "environment": INFISICAL_ENVIRONMENT,
                "secretPath": INFISICAL_SECRET_PATH,
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        secret_value = resp.json()["secret"]["secretValue"]
        print(f"✓ {name} = {secret_value[:6]}...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
