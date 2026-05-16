from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus

from relaymd.orchestrator.db import get_sessionmaker

from ._worker_endpoints_test_helpers import app_client, make_settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/workers/register",
            {"platform": "hpc", "gpu_model": "A100", "gpu_count": 1, "vram_gb": 80},
        ),
        ("/workers/11111111-1111-1111-1111-111111111111/heartbeat", None),
        ("/workers/22222222-2222-2222-2222-222222222222/deregister", None),
        ("/jobs/request", None),
        ("/jobs/33333333-3333-3333-3333-333333333333/start", None),
        (
            "/jobs/44444444-4444-4444-4444-444444444444/checkpoint",
            {"checkpoint_path": "jobs/x/checkpoints/latest"},
        ),
        ("/jobs/55555555-5555-5555-5555-555555555555/complete", None),
        ("/jobs/66666666-6666-6666-6666-666666666666/fail", None),
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
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
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
        assert returned_worker_id == placeholder_id

        listed = await client.get("/workers", headers=headers)
        assert listed.status_code == 200
        payload = listed.json()
        assert len(payload) == 1

        real_worker = payload[0]
        assert real_worker["id"] == placeholder_id
        assert real_worker["status"] == "active"
        assert real_worker["vram_gb"] == 80
        assert real_worker["provider_id"] == "gilbreth:99001"
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


@pytest.mark.asyncio
async def test_handoff_start_and_complete_requeues_job() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        register_response = await client.post(
            "/workers/register",
            headers=headers,
            json={"platform": "hpc", "gpu_model": "A100", "gpu_count": 1, "vram_gb": 80},
        )
        worker_id = register_response.json()["worker_id"]

        async with get_sessionmaker()() as session:
            job = Job(title="handoff", input_bundle_path="jobs/h/input/bundle.tar.gz")
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
        start_response = await client.post(f"/jobs/{job_id}/start", headers=headers)
        assert start_response.status_code == 204

        handoff_start_response = await client.post(
            f"/jobs/{job_id}/handoff/start",
            headers=headers,
            json={"reason": "allocation_deadline", "progress": 0.5, "progress_codes": ["ok"]},
        )
        assert handoff_start_response.status_code == 204

        handoff_complete_response = await client.post(
            f"/jobs/{job_id}/handoff/complete",
            headers=headers,
            json={"checkpoint_path": "jobs/h/checkpoints/latest"},
        )
        assert handoff_complete_response.status_code == 204

        async with get_sessionmaker()() as session:
            requeued = await session.get(Job, job_id)
            assert requeued is not None
            assert requeued.status == JobStatus.queued
            assert requeued.assigned_worker_id is None
            assert requeued.latest_checkpoint_manifest_path == "jobs/h/checkpoints/latest"
