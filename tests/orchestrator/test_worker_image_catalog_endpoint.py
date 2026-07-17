from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from relaymd.orchestrator.config import OrchestratorSettings, WorkerImageProfile
from relaymd.orchestrator.main import create_app


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    async def _skip_tailscale_startup(_settings: OrchestratorSettings):
        return None

    with patch(
        "relaymd.orchestrator.main._ensure_tailscale_running",
        new=_skip_tailscale_startup,
    ):
        app = create_app(settings, start_background_tasks=False)
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client


@pytest.mark.asyncio
async def test_worker_image_catalog_requires_authentication() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        slurm_cluster_configs=[],
    )

    async with app_client(settings) as client:
        response = await client.get("/config/worker-images")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_worker_image_catalog_returns_configured_profiles() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        worker_image_profiles={
            "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
            "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
        },
        slurm_cluster_configs=[],
    )

    async with app_client(settings) as client:
        response = await client.get("/config/worker-images", headers={"X-API-Token": "test-token"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "default_worker_image": "atom-openmm",
        "worker_images": [
            {"key": "atom-openmm", "display_name": "AToM-OpenMM"},
            {"key": "gcncmcmd", "display_name": "GCNCMC-MD"},
        ],
    }
