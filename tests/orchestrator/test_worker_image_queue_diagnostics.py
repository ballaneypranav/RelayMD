from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus

from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    async def _skip_tailscale_startup(_settings: OrchestratorSettings) -> None:
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
async def test_partial_salad_configuration_does_not_unblock_create_or_requeue() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        slurm_cluster_configs=[],
        salad_container_group="group",
    )
    headers = {"X-API-Token": "test-token"}
    async with app_client(settings) as client:
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={"title": "blocked", "input_bundle_path": "jobs/blocked/input/bundle.tar.gz"},
        )
        assert create_response.status_code == status.HTTP_200_OK
        job_id = create_response.json()["id"]
        assert (
            create_response.json()["queue_blocked_reason"] == "no_compatible_worker_image_clusters"
        )

        async with get_sessionmaker()() as session:
            job = await session.get(Job, UUID(job_id))
            assert job is not None
            job.status = JobStatus.failed
            session.add(job)
            await session.commit()

        requeue_response = await client.post(f"/jobs/{job_id}/requeue", headers=headers)
        assert requeue_response.status_code == status.HTTP_200_OK
        assert (
            requeue_response.json()["queue_blocked_reason"] == "no_compatible_worker_image_clusters"
        )
