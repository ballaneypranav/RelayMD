from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.main import _frontend_dist_dir, _resolve_frontend_asset_path, create_app


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    app = create_app(settings, start_background_tasks=False)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def make_settings() -> OrchestratorSettings:
    return OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        slurm_cluster_configs=[],
    )


@pytest.mark.asyncio
async def test_frontend_config_returns_non_secret_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELAYMD_REFRESH_INTERVAL_SECONDS", "12")
    monkeypatch.setenv("RELAYMD_FRONTEND_API_BASE_URL", "http://127.0.0.1:36159/")

    async with app_client(make_settings()) as client:
        response = await client.get("/config/frontend")

    assert response.status_code == 200
    assert response.json() == {
        "api_base_url": "http://127.0.0.1:36159",
        "refresh_interval_seconds": 12,
    }
    assert "api_token" not in response.text


def test_frontend_config_rejects_non_loopback_api_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELAYMD_FRONTEND_API_BASE_URL", "http://example.test")

    with pytest.raises(ValueError, match="loopback-local"):
        create_app(make_settings(), start_background_tasks=False)


def test_frontend_dist_dir_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>frontend</body></html>")
    monkeypatch.setenv("RELAYMD_FRONTEND_DIST_DIR", str(dist_dir))

    assert _frontend_dist_dir() == dist_dir


@pytest.mark.asyncio
async def test_root_redirects_to_app_jobs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>frontend</body></html>")
    monkeypatch.setenv("RELAYMD_FRONTEND_DIST_DIR", str(dist_dir))

    async with app_client(make_settings()) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/jobs"


@pytest.mark.asyncio
async def test_spa_fallback_serves_index_for_app_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>spa-shell</body></html>")
    monkeypatch.setenv("RELAYMD_FRONTEND_DIST_DIR", str(dist_dir))

    async with app_client(make_settings()) as client:
        response = await client.get("/app/jobs")

    assert response.status_code == 200
    assert "spa-shell" in response.text


@pytest.mark.asyncio
async def test_api_prefixes_are_not_intercepted_by_spa_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>spa-shell</body></html>")
    monkeypatch.setenv("RELAYMD_FRONTEND_DIST_DIR", str(dist_dir))

    async with app_client(make_settings()) as client:
        response = await client.get("/config/not-a-real-endpoint")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_non_app_non_api_routes_are_not_intercepted_by_spa_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>spa-shell</body></html>")
    monkeypatch.setenv("RELAYMD_FRONTEND_DIST_DIR", str(dist_dir))

    async with app_client(make_settings()) as client:
        response = await client.get("/dashboard/jobs")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


def test_frontend_asset_resolution_rejects_path_traversal(tmp_path: Path) -> None:
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("do not serve")

    assert _resolve_frontend_asset_path(dist_dir, "../../secret.txt") is None
