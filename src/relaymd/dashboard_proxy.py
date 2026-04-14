from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.security import HTTPBasic

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


@dataclass(frozen=True)
class DashboardProxySettings:
    upstream_url: str
    upstream_api_token: str
    username: str
    password: str
    timeout_seconds: float = 30.0


def create_dashboard_proxy_app(
    settings: DashboardProxySettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    security = HTTPBasic(auto_error=False)
    app = FastAPI()

    def _unauthorized_response() -> Response:
        return Response(
            content="Authentication required",
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="RelayMD Dashboard"'},
        )

    @app.middleware("http")
    async def require_basic_auth(request: Request, call_next) -> Response:
        credentials = await security(request)
        if credentials is None:
            return _unauthorized_response()
        username_ok = secrets.compare_digest(credentials.username, settings.username)
        password_ok = secrets.compare_digest(credentials.password, settings.password)
        if not (username_ok and password_ok):
            return _unauthorized_response()
        return await call_next(request)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy(path: str, request: Request) -> Response:
        upstream_url = settings.upstream_url.rstrip("/")
        request_url = f"{upstream_url}/{path}" if path else upstream_url
        if request.url.query:
            request_url = f"{request_url}?{request.url.query}"

        forwarded_headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "authorization"
        }
        forwarded_headers["x-forwarded-proto"] = request.url.scheme
        forwarded_headers["x-forwarded-host"] = request.headers.get("host", "")
        forwarded_headers["x-api-token"] = settings.upstream_api_token
        forwarded_headers["authorization"] = f"Bearer {settings.upstream_api_token}"

        async with httpx.AsyncClient(
            transport=transport,
            timeout=settings.timeout_seconds,
            follow_redirects=False,
        ) as client:
            upstream_response = await client.request(
                request.method,
                request_url,
                headers=forwarded_headers,
                content=await request.body(),
            )

        response_headers = {
            key: value
            for key, value in upstream_response.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )

    return app
