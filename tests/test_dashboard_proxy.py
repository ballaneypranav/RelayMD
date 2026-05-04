from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from relaymd.dashboard_proxy import DashboardProxySettings, create_dashboard_proxy_app

SETTINGS = DashboardProxySettings(
    upstream_url="http://upstream.test",
    upstream_api_token="relaymd-token",
    username="operator",
    password="secret",
)


def _make_app(**kwargs) -> FastAPI:
    return create_dashboard_proxy_app(DashboardProxySettings(**{
        "upstream_url": "http://upstream.test",
        "upstream_api_token": "relaymd-token",
        "username": "operator",
        "password": "secret",
        **kwargs,
    }))


async def _login(client: AsyncClient, username="operator", password="secret", next_url="/") -> str:
    resp = await client.post(
        "/login",
        data={"username": username, "password": password, "next": next_url},
        follow_redirects=False,
    )
    return resp.cookies.get("relaymd_session", "")


@pytest.mark.asyncio
async def test_unauthenticated_request_redirects_to_login() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert "/login" in response.headers["location"]


@pytest.mark.asyncio
async def test_login_page_returns_html_form() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text
    assert 'type="password"' in response.text


@pytest.mark.asyncio
async def test_successful_login_sets_session_cookie() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.post(
            "/login",
            data={"username": "operator", "password": "secret", "next": "/"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "relaymd_session" in response.cookies


@pytest.mark.asyncio
async def test_failed_login_redirects_with_error_no_cookie() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.post(
            "/login",
            data={"username": "operator", "password": "wrong", "next": "/"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "error=1" in response.headers["location"]
    assert "relaymd_session" not in response.cookies


@pytest.mark.asyncio
async def test_authenticated_session_proxies_requests() -> None:
    upstream = FastAPI()

    @upstream.get("/healthz")
    async def healthz(request: Request) -> dict[str, str]:
        return {
            "status": "ok",
            "x_api_token": request.headers.get("x-api-token", ""),
            "authorization": request.headers.get("authorization", ""),
        }

    proxy = create_dashboard_proxy_app(SETTINGS, transport=ASGITransport(app=upstream))

    async with AsyncClient(transport=ASGITransport(app=proxy), base_url="http://proxy.test") as client:
        session_cookie = await _login(client)
        response = await client.get(
            "/healthz",
            cookies={"relaymd_session": session_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "x_api_token": "relaymd-token",
        "authorization": "Bearer relaymd-token",
    }


@pytest.mark.asyncio
async def test_session_cookie_not_forwarded_to_upstream() -> None:
    upstream = FastAPI()

    @upstream.get("/check")
    async def check(request: Request) -> dict[str, str]:
        return {"cookie": request.headers.get("cookie", "")}

    proxy = create_dashboard_proxy_app(SETTINGS, transport=ASGITransport(app=upstream))

    async with AsyncClient(transport=ASGITransport(app=proxy), base_url="http://proxy.test") as client:
        session_cookie = await _login(client)
        response = await client.get(
            "/check",
            cookies={"relaymd_session": session_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert "relaymd_session" not in response.json()["cookie"]


@pytest.mark.asyncio
async def test_logout_clears_session() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        session_cookie = await _login(client)

        logout_resp = await client.get(
            "/logout",
            cookies={"relaymd_session": session_cookie},
            follow_redirects=False,
        )
        assert logout_resp.status_code == 303

        # The cleared/absent session should not grant access
        cleared_cookie = logout_resp.cookies.get("relaymd_session", "invalid")
        after_resp = await client.get(
            "/workers",
            cookies={"relaymd_session": cleared_cookie},
            follow_redirects=False,
        )

    assert after_resp.status_code == 303
    assert "/login" in after_resp.headers["location"]


@pytest.mark.asyncio
async def test_next_param_redirect_after_login() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.post(
            "/login",
            data={"username": "operator", "password": "secret", "next": "/workers"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/workers"


@pytest.mark.asyncio
async def test_open_redirect_is_blocked() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        response = await client.post(
            "/login",
            data={"username": "operator", "password": "secret", "next": "https://evil.com"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location == "/" or location.startswith("http://proxy.test/")
    assert "evil.com" not in location


@pytest.mark.asyncio
async def test_invalid_credentials_do_not_grant_access() -> None:
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://proxy.test") as client:
        bad_cookie = await _login(client, password="wrong")
        response = await client.get(
            "/workers",
            cookies={"relaymd_session": bad_cookie},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "/login" in response.headers["location"]
