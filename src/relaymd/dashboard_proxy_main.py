from __future__ import annotations

import os

import uvicorn

from relaymd.dashboard_proxy import DashboardProxySettings, create_dashboard_proxy_app


def start() -> None:
    api_token = os.getenv("RELAYMD_API_TOKEN", "").strip()
    username = os.getenv("RELAYMD_DASHBOARD_USERNAME", "").strip()
    password = os.getenv("RELAYMD_DASHBOARD_PASSWORD", "").strip()

    if not api_token:
        raise SystemExit("RELAYMD_API_TOKEN is required")
    if not username:
        raise SystemExit("RELAYMD_DASHBOARD_USERNAME is required")
    if not password:
        raise SystemExit("RELAYMD_DASHBOARD_PASSWORD is required")

    settings = DashboardProxySettings(
        upstream_url=os.getenv("RELAYMD_PROXY_UPSTREAM_URL", "http://127.0.0.1:36158"),
        upstream_api_token=api_token,
        username=username,
        password=password,
    )

    uvicorn.run(
        create_dashboard_proxy_app(settings),
        host=os.getenv("RELAYMD_PROXY_HOST", "127.0.0.1"),
        port=int(os.getenv("RELAYMD_PROXY_PORT", "36159")),
    )
