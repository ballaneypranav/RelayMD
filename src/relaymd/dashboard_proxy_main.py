from __future__ import annotations

import os
from typing import Any

import uvicorn

from relaymd.core_secret_management import DashboardProxySecretManager
from relaymd.dashboard_proxy import DashboardProxySettings, create_dashboard_proxy_app

INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "prod"
INFISICAL_SECRET_PATH = "/RelayMD"


def _get_infisical_client_dependencies() -> tuple[type[Any], type[Any], type[Any]]:
    try:
        from infisical_client import ClientSettings, InfisicalClient
        from infisical_client.schemas import GetSecretOptions
    except ImportError as exc:
        raise RuntimeError("INFISICAL_TOKEN is set but infisical-python is not installed.") from exc

    return ClientSettings, InfisicalClient, GetSecretOptions


def load_proxy_settings() -> DashboardProxySettings:
    machine_token = os.getenv("INFISICAL_TOKEN", "").strip()
    if not machine_token:
        raise RuntimeError("INFISICAL_TOKEN is required")

    secret_manager = DashboardProxySecretManager(
        machine_token=machine_token,
        dependency_loader=_get_infisical_client_dependencies,
        base_url=INFISICAL_BASE_URL,
        workspace_id=INFISICAL_WORKSPACE_ID,
        environment=INFISICAL_ENVIRONMENT,
        secret_path=INFISICAL_SECRET_PATH,
    )
    secret_values = secret_manager.fetch_proxy_values()

    return DashboardProxySettings(
        upstream_url=os.getenv("RELAYMD_PROXY_UPSTREAM_URL", "http://127.0.0.1:36158"),
        upstream_api_token=secret_values["api_token"],
        username=secret_values["dashboard_username"],
        password=secret_values["dashboard_password"],
        session_secret=secret_values.get("dashboard_session_secret") or None,
    )


def start() -> None:
    settings = load_proxy_settings()

    uvicorn.run(
        create_dashboard_proxy_app(settings),
        host=os.getenv("RELAYMD_PROXY_HOST", "127.0.0.1"),
        port=int(os.getenv("RELAYMD_PROXY_PORT", "36159")),
    )
