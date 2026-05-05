from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus

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
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="test",
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
async def test_request_ignores_pending_slurm_placeholder_workers() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        register = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "salad",
                "gpu_model": "NVIDIA A10",
                "gpu_count": 1,
                "vram_gb": 24,
            },
        )
        worker_id = register.json()["worker_id"]

        async with get_sessionmaker()() as session:
            session.add(
                Worker(
                    platform=Platform.hpc,
                    gpu_model="NVIDIA H100",
                    gpu_count=8,
                    vram_gb=0,
                    status=WorkerStatus.queued,
                    provider_id="gilbreth:placeholder",
                    last_heartbeat=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            session.add(
                Job(
                    title="train-with-placeholder",
                    input_bundle_path="jobs/placeholder/input/bundle.tar.gz",
                    status=JobStatus.queued,
                )
            )
            await session.commit()

        response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "assigned"


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
async def test_register_worker_with_provider_id_activates_matching_placeholder() -> None:
    """When a SLURM worker registers with its provider_id, the matching queued
    placeholder is activated in-place: same UUID, status=active, real vram_gb."""
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        # Seed a placeholder the way the provisioning service would.
        async with get_sessionmaker()() as session:
            placeholder = Worker(
                platform=Platform.hpc,
                gpu_model="a100",
                gpu_count=2,
                vram_gb=0,
                status=WorkerStatus.queued,
                provider_id="gilbreth:99001",
                last_heartbeat=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(placeholder)
            await session.commit()
            await session.refresh(placeholder)
            placeholder_id = str(placeholder.id)

        # The real worker starts and registers with its full provider_id.
        with patch(
            "relaymd.orchestrator.services.worker_lifecycle_service.logger.info"
        ) as info_mock:
            register_response = await client.post(
                "/workers/register",
                headers=headers,
                json={
                    "platform": "hpc",
                    "gpu_model": "a100",
                    "gpu_count": 2,
                    "vram_gb": 80,
                    "provider_id": "gilbreth:99001",
                },
            )
        assert register_response.status_code == 200
        returned_worker_id = register_response.json()["worker_id"]

        # Same UUID — placeholder was activated in place, not recreated.
        assert returned_worker_id == placeholder_id

        # Only one worker row should exist.
        listed = await client.get("/workers", headers=headers)
        assert listed.status_code == 200
        payload = listed.json()
        assert len(payload) == 1

        real_worker = payload[0]
        assert real_worker["id"] == placeholder_id
        assert real_worker["status"] == "active"
        assert real_worker["vram_gb"] == 80  # updated from real GPU
        assert real_worker["provider_id"] == "gilbreth:99001"  # preserved
        info_mock.assert_any_call(
            "queued_placeholder_activated",
            provider_id="gilbreth:99001",
            worker_id=placeholder_id,
            platform="hpc",
        )


@pytest.mark.asyncio
async def test_list_workers_requires_api_token() -> None:
    settings = make_settings()

    async with app_client(settings) as (_app, client):
        response = await client.get("/workers")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_late_worker_callbacks_return_typed_conflicts() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        async with get_sessionmaker()() as session:
            job = Job(
                title="already-done",
                input_bundle_path="jobs/done/input/bundle.tar.gz",
                status=JobStatus.completed,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

        checkpoint_response = await client.post(
            f"/jobs/{job.id}/checkpoint",
            headers=headers,
            json={"checkpoint_path": "jobs/done/checkpoints/latest"},
        )
        assert checkpoint_response.status_code == 409
        assert checkpoint_response.json()["error"] == "job_transition_conflict"

        complete_response = await client.post(f"/jobs/{job.id}/complete", headers=headers)
        assert complete_response.status_code == 409
        assert complete_response.json()["error"] == "job_transition_conflict"

        fail_response = await client.post(f"/jobs/{job.id}/fail", headers=headers)
        assert fail_response.status_code == 409
        assert fail_response.json()["error"] == "job_transition_conflict"
