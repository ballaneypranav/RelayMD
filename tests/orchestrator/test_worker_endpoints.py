from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus, Platform, Worker

from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.main import create_app
from relaymd.orchestrator.scheduler import reap_stale_workers


@asynccontextmanager
async def app_client(settings: OrchestratorSettings):
    app = create_app(settings, start_background_tasks=False)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


def make_settings() -> OrchestratorSettings:
    return OrchestratorSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
    )


@pytest.mark.asyncio
async def test_worker_flow_register_request_heartbeat_checkpoint_complete() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        register_response = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "A100",
                "gpu_count": 2,
                "vram_gb": 80,
            },
        )
        assert register_response.status_code == 200
        worker_id = register_response.json()["worker_id"]

        async with get_sessionmaker()() as session:
            job = Job(title="train-1", input_bundle_path="jobs/1/input/bundle.tar.gz")
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        request_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert request_response.status_code == 200
        assert request_response.json()["status"] == "assigned"
        assert request_response.json()["job_id"] == str(job_id)
        assert request_response.json()["input_bundle_path"] == "jobs/1/input/bundle.tar.gz"
        assert request_response.json()["latest_checkpoint_path"] is None

        heartbeat_response = await client.post(f"/workers/{worker_id}/heartbeat", headers=headers)
        assert heartbeat_response.status_code == 204

        checkpoint_response = await client.post(
            f"/jobs/{job_id}/checkpoint",
            headers=headers,
            json={"checkpoint_path": "jobs/1/checkpoints/latest"},
        )
        assert checkpoint_response.status_code == 204

        complete_response = await client.post(f"/jobs/{job_id}/complete", headers=headers)
        assert complete_response.status_code == 204

        async with get_sessionmaker()() as session:
            db_job = await session.get(Job, job_id)
            assert db_job is not None
            assert db_job.status == JobStatus.completed
            assert db_job.latest_checkpoint_path == "jobs/1/checkpoints/latest"
            assert db_job.last_checkpoint_at is not None


@pytest.mark.asyncio
async def test_stale_worker_reaper_requeues_jobs() -> None:
    settings = make_settings()

    async with app_client(settings) as (app, _client):
        with freeze_time("2026-01-01T12:00:00"):
            stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)

            async with get_sessionmaker()() as session:
                worker = Worker(
                    platform=Platform.hpc,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=80,
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="train-2",
                    input_bundle_path="jobs/2/input/bundle.tar.gz",
                    status=JobStatus.assigned,
                    assigned_worker_id=worker.id,
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                job_id = job.id
                worker_id = worker.id

            stale_count = await reap_stale_workers(app.state.settings)
            assert stale_count == 1

            async with get_sessionmaker()() as session:
                requeued_job = await session.get(Job, job_id)
                assert requeued_job is not None
                assert requeued_job.status == JobStatus.queued
                assert requeued_job.assigned_worker_id is None

                deleted_worker = await session.get(Worker, worker_id)
                assert deleted_worker is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/workers/register",
            {"platform": "hpc", "gpu_model": "A100", "gpu_count": 1, "vram_gb": 80},
        ),
        (f"/workers/{uuid4()}/heartbeat", None),
        (f"/workers/{uuid4()}/deregister", None),
        ("/jobs/request", None),
        (f"/jobs/{uuid4()}/checkpoint", {"checkpoint_path": "jobs/x/checkpoints/latest"}),
        (f"/jobs/{uuid4()}/complete", None),
        (f"/jobs/{uuid4()}/fail", None),
    ],
)
async def test_worker_endpoints_require_api_token(
    path: str, payload: dict[str, object] | None
) -> None:
    settings = make_settings()

    async with app_client(settings) as (_app, client):
        response = await client.post(path, json=payload)
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_request_returns_no_job_available_when_queue_empty() -> None:
    settings = make_settings()

    async with app_client(settings) as (_app, client):
        register_response = await client.post(
            "/workers/register",
            headers={"X-API-Token": "test-token"},
            json={
                "platform": "hpc",
                "gpu_model": "A100",
                "gpu_count": 1,
                "vram_gb": 80,
            },
        )
        worker_id = register_response.json()["worker_id"]
        response = await client.post(
            "/jobs/request",
            headers={"X-API-Token": "test-token"},
            params={"worker_id": worker_id},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "no_job_available"}


@pytest.mark.asyncio
async def test_request_only_assigns_to_highest_scoring_idle_worker() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        higher_register = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "NVIDIA A100",
                "gpu_count": 4,
                "vram_gb": 80,
            },
        )
        higher_worker_id = higher_register.json()["worker_id"]
        lower_register = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "salad",
                "gpu_model": "NVIDIA A10",
                "gpu_count": 1,
                "vram_gb": 24,
            },
        )
        lower_worker_id = lower_register.json()["worker_id"]

        async with get_sessionmaker()() as session:
            job = Job(title="train-priority", input_bundle_path="jobs/priority/input/bundle.tar.gz")
            session.add(job)
            await session.commit()

        lower_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": lower_worker_id},
        )
        assert lower_response.status_code == 200
        assert lower_response.json() == {"status": "no_job_available"}

        higher_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": higher_worker_id},
        )
        assert higher_response.status_code == 200
        assert higher_response.json()["status"] == "assigned"


@pytest.mark.asyncio
async def test_list_workers_returns_registered_workers() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        first_register = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "NVIDIA A100",
                "gpu_count": 4,
                "vram_gb": 80,
            },
        )
        second_register = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "salad",
                "gpu_model": "NVIDIA A10",
                "gpu_count": 1,
                "vram_gb": 24,
            },
        )

        listed = await client.get("/workers", headers=headers)
        assert listed.status_code == 200
        payload = listed.json()
        assert len(payload) == 2
        assert payload[0]["id"] == second_register.json()["worker_id"]
        assert payload[1]["id"] == first_register.json()["worker_id"]


@pytest.mark.asyncio
async def test_list_workers_requires_api_token() -> None:
    settings = make_settings()

    async with app_client(settings) as (_app, client):
        response = await client.get("/workers")
        assert response.status_code == 401
