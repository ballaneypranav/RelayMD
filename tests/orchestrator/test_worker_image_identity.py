from datetime import UTC, datetime

import pytest
from fastapi import status
from relaymd.models import Platform, Worker, WorkerStatus
from sqlmodel import select

from relaymd.orchestrator.db import get_sessionmaker

from ._worker_endpoints_test_helpers import app_client, make_settings


@pytest.mark.asyncio
async def test_job_creation_resolves_default_worker_image() -> None:
    settings = make_settings()
    async with app_client(settings) as (_app, client):
        response = await client.post(
            "/jobs",
            headers={"X-API-Token": "test-token"},
            json={"title": "image-default", "input_bundle_path": "jobs/input.tar.gz"},
        )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["worker_image_key"] == "atom-openmm"


@pytest.mark.asyncio
async def test_job_creation_rejects_explicit_blank_worker_image() -> None:
    settings = make_settings()
    async with app_client(settings) as (_app, client):
        response = await client.post(
            "/jobs",
            headers={"X-API-Token": "test-token"},
            json={
                "title": "blank-image",
                "input_bundle_path": "jobs/input.tar.gz",
                "worker_image_key": "",
            },
        )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_placeholder_activation_requires_matching_image_key() -> None:
    settings = make_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    async with app_client(settings) as (_app, client):
        async with get_sessionmaker()() as session:
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:123",
                    worker_image_key="gcncmcmd",
                    last_heartbeat=now,
                )
            )
            await session.commit()
        response = await client.post(
            "/workers/register",
            headers={"X-API-Token": "test-token"},
            json={
                "platform": "hpc",
                "gpu_model": "A100",
                "gpu_count": 1,
                "vram_gb": 80,
                "provider_id": "gilbreth:123",
                "worker_image_key": "atom-openmm",
            },
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        async with get_sessionmaker()() as session:
            placeholder = (
                await session.exec(
                    select(Worker).where(
                        Worker.provider_id == "gilbreth:123",
                        Worker.status == WorkerStatus.queued,
                    )
                )
            ).one()
            assert placeholder is not None
            assert placeholder.worker_image_key == "gcncmcmd"
            conflicting_workers = (
                await session.exec(
                    select(Worker).where(
                        Worker.provider_id == "gilbreth:123",
                        Worker.status == WorkerStatus.active,
                    )
                )
            ).all()
            assert conflicting_workers == []
