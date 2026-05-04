from __future__ import annotations

import hashlib
import html
import secrets
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

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

_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>RelayMD Dashboard — Login</title>
  <style>
    body {{ font-family: sans-serif; display: flex; justify-content: center;
            align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
    form {{ background: white; padding: 2rem; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,.1); min-width: 300px; }}
    h1 {{ margin-top: 0; font-size: 1.25rem; }}
    label {{ display: block; margin-bottom: .25rem; font-size: .875rem; }}
    input {{ width: 100%; box-sizing: border-box; padding: .5rem;
             margin-bottom: 1rem; border: 1px solid #ccc; border-radius: 4px; }}
    button {{ width: 100%; padding: .6rem; background: #2563eb; color: white;
              border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }}
    button:hover {{ background: #1d4ed8; }}
    .error {{ color: #dc2626; margin-bottom: 1rem; font-size: .875rem; }}
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>RelayMD Dashboard</h1>
    {error_html}
    <input type="hidden" name="next" value="{next_url}">
    <label for="username">Username</label>
    <input type="text" id="username" name="username" autocomplete="username" required>
    <label for="password">Password</label>
    <input type="password" id="password" name="password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
  </form>
</body>
</html>"""


@dataclass(frozen=True)
class DashboardProxySettings:
    upstream_url: str
    upstream_api_token: str
    username: str
    password: str
    timeout_seconds: float = 30.0
    session_secret: str | None = None


class _SessionAuthMiddleware:
    """Pure ASGI middleware that enforces session authentication.

    Must run after SessionMiddleware so that scope["session"] is populated.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")
        if path == "/login":
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})
        if not session.get("authenticated"):
            next_path = path
            query_string = scope.get("query_string", b"").decode()
            if query_string:
                next_path = f"{next_path}?{query_string}"
            response = RedirectResponse(
                f"/login?next={quote(next_path, safe='')}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def create_dashboard_proxy_app(
    settings: DashboardProxySettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    # Derive a stable secret from the password so sessions survive restarts.
    # Rotating the password automatically invalidates all sessions.
    _secret = (
        settings.session_secret
        or hashlib.sha256(f"relaymd-dashboard-session:{settings.password}".encode()).hexdigest()
    )

    app = FastAPI()

    # Registration order matters: last add_middleware = outermost layer.
    # We want: request → SessionMiddleware → _SessionAuthMiddleware → routes
    app.add_middleware(_SessionAuthMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=_secret,
        session_cookie="relaymd_session",
        max_age=None,
        https_only=False,  # plain HTTP over Tailscale
        same_site="lax",
    )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        next_url = html.escape(request.query_params.get("next", "/"), quote=True)
        error_html = (
            "<p class='error'>Invalid username or password.</p>"
            if request.query_params.get("error")
            else ""
        )
        return HTMLResponse(_LOGIN_HTML.format(next_url=next_url, error_html=error_html))

    @app.post("/login")
    async def login_submit(request: Request) -> Response:
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        next_url = str(form.get("next", "/"))

        username_ok = secrets.compare_digest(username, settings.username)
        password_ok = secrets.compare_digest(password, settings.password)

        if not (username_ok and password_ok):
            safe_next = quote(next_url, safe="/")
            return RedirectResponse(
                f"/login?next={safe_next}&error=1",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        # Guard against open redirects: only allow relative paths.
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/"

        request.session["authenticated"] = True
        return RedirectResponse(next_url, status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/logout")
    async def logout(request: Request) -> Response:
        request.session.clear()
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

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
            if key.lower() not in HOP_BY_HOP_HEADERS
            and key.lower() != "authorization"
            and key.lower() != "cookie"
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
