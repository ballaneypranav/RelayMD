#!/usr/bin/env python3
"""Validate required Infisical secrets are accessible via machine identity auth."""

from __future__ import annotations

import os
import sys

from relaymd.secret_management import InfisicalSecretManager

INFISICAL_BASE_URL = os.environ.get("INFISICAL_BASE_URL", "https://app.infisical.com")
INFISICAL_ENVIRONMENT = os.environ.get("INFISICAL_ENVIRONMENT", "production")
INFISICAL_SECRET_PATH = os.environ.get("INFISICAL_SECRET_PATH", "/RelayMD")
DEFAULT_INFISICAL_PROJECT_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
EXPECTED_SECRETS = [
    "AXIOM_TOKEN",
    "B2_APPLICATION_KEY",
    "B2_APPLICATION_KEY_ID",
    "B2_ENDPOINT",
    "BUCKET_NAME",
    "RELAYMD_API_TOKEN",
    "RELAYMD_ORCHESTRATOR_URL",
    "TAILSCALE_AUTH_KEY",
]


def _get_infisical_client_dependencies():
    from infisical_client import ClientSettings, InfisicalClient
    from infisical_client.schemas import GetSecretOptions

    return ClientSettings, InfisicalClient, GetSecretOptions


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(1)
    return value


def main() -> int:
    client_id = get_required_env("INFISICAL_CLIENT_ID")
    client_secret = get_required_env("INFISICAL_CLIENT_SECRET")
    project_id = os.environ.get("INFISICAL_PROJECT_ID", DEFAULT_INFISICAL_PROJECT_ID)
    machine_token = f"{client_id}:{client_secret}"

    try:
        manager = InfisicalSecretManager(
            machine_token=machine_token,
            dependency_loader=_get_infisical_client_dependencies,
            base_url=INFISICAL_BASE_URL,
            workspace_id=project_id,
            environment=INFISICAL_ENVIRONMENT,
            secret_path=INFISICAL_SECRET_PATH,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            "Infisical auth failed. Check INFISICAL_CLIENT_ID and "
            "INFISICAL_CLIENT_SECRET for a valid Universal Auth machine identity.",
            file=sys.stderr,
        )
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        secret_values = manager.fetch_mapped_secrets(
            required={name: name for name in EXPECTED_SECRETS}
        )
        for name in EXPECTED_SECRETS:
            secret_value = secret_values[name]
            if not secret_value:
                print(f"Secret {name} is empty", file=sys.stderr)
                raise SystemExit(1)
            print(f"✓ {name} = {secret_value[:6]}...")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read secrets: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
