from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from relaymd.dashboard_proxy import DashboardProxySettings, create_dashboard_proxy_app


def _basic_auth(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.mark.asyncio
async def test_dashboard_proxy_requires_basic_auth() -> None:
    app = create_dashboard_proxy_app(
        DashboardProxySettings(
            upstream_url="http://upstream.test",
            upstream_api_token="relaymd-token",
            username="operator",
            password="secret",
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://proxy.test"
    ) as client:
        response = await client.get("/")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="RelayMD Dashboard"'


@pytest.mark.asyncio
async def test_dashboard_proxy_forwards_authorized_requests() -> None:
    upstream = FastAPI()

    @upstream.get("/healthz")
    async def healthz(request: Request) -> dict[str, str]:
        return {
            "status": "ok",
            "x_api_token": request.headers.get("x-api-token", ""),
            "authorization": request.headers.get("authorization", ""),
        }

    proxy = create_dashboard_proxy_app(
        DashboardProxySettings(
            upstream_url="http://upstream.test",
            upstream_api_token="relaymd-token",
            username="operator",
            password="secret",
        ),
        transport=ASGITransport(app=upstream),
    )

    async with AsyncClient(
        transport=ASGITransport(app=proxy), base_url="http://proxy.test"
    ) as client:
        response = await client.get("/healthz", headers=_basic_auth("operator", "secret"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "x_api_token": "relaymd-token",
        "authorization": "Bearer relaymd-token",
    }


@pytest.mark.asyncio
async def test_dashboard_proxy_rejects_invalid_credentials() -> None:
    app = create_dashboard_proxy_app(
        DashboardProxySettings(
            upstream_url="http://upstream.test",
            upstream_api_token="relaymd-token",
            username="operator",
            password="secret",
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://proxy.test"
    ) as client:
        response = await client.get("/workers", headers=_basic_auth("operator", "wrong"))

    assert response.status_code == 401
