from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from relaymd.models import Job, JobStatus

from relaymd import __version__
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
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
                yield app, client


def make_settings() -> OrchestratorSettings:
    return OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        slurm_cluster_configs=[],
    )


def make_slurm_settings() -> OrchestratorSettings:
    return OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="client-id:client-secret",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab",
                ssh_host="host-a",
                ssh_username="user-a",
                gpu_type="a100",
                gpu_count=1,
                sif_path="/tmp/a.sif",
            ),
            ClusterConfig(
                name="anvil",
                partition="gpu",
                account="lab",
                ssh_host="host-b",
                ssh_username="user-b",
                gpu_type="a100",
                gpu_count=1,
                sif_path="/tmp/b.sif",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_healthz_no_auth_required() -> None:
    async with app_client(make_settings()) as (_app, client):
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["version"] == __version__


@pytest.mark.asyncio
async def test_operator_endpoints_require_api_token() -> None:
    async with app_client(make_settings()) as (_app, client):
        create_resp = await client.post("/jobs", json={"title": "a", "input_bundle_path": "x"})
        assert create_resp.status_code == 401
        assert (await client.get("/jobs")).status_code == 401
        assert (await client.get("/jobs/00000000-0000-0000-0000-000000000000")).status_code == 401
        assert (
            await client.delete("/jobs/00000000-0000-0000-0000-000000000000")
        ).status_code == 401
        assert (
            await client.post("/jobs/00000000-0000-0000-0000-000000000000/requeue")
        ).status_code == 401


@pytest.mark.asyncio
async def test_create_list_get_and_cancel_paths() -> None:
    headers = {"X-API-Token": "test-token"}

    async with app_client(make_settings()) as (_app, client):
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={"title": "job-1", "input_bundle_path": "jobs/1/input/bundle.tar.gz"},
        )
        assert create_response.status_code == 200
        created_job = create_response.json()
        job_id = created_job["id"]
        job_id_uuid = UUID(job_id)
        assert created_job["status"] == "queued"

        second_create_response = await client.post(
            "/jobs",
            headers=headers,
            json={"title": "job-2", "input_bundle_path": "jobs/2/input/bundle.tar.gz"},
        )
        assert second_create_response.status_code == 200

        duplicate_id_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "id": job_id,
                "title": "duplicate",
                "input_bundle_path": "jobs/dup/input/bundle.tar.gz",
            },
        )
        assert duplicate_id_response.status_code == 409
        assert duplicate_id_response.json()["job_id"] == job_id
        assert "already exists" in duplicate_id_response.json()["message"]

        list_response = await client.get("/jobs", headers=headers)
        assert list_response.status_code == 200
        listed_jobs = list_response.json()
        assert len(listed_jobs) == 2
        assert listed_jobs[0]["title"] == "job-2"
        assert listed_jobs[1]["title"] == "job-1"

        get_response = await client.get(f"/jobs/{job_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["id"] == job_id

        cancel_queued_response = await client.delete(f"/jobs/{job_id}", headers=headers)
        assert cancel_queued_response.status_code == 204

        async with get_sessionmaker()() as session:
            cancelled_queued_job = await session.get(Job, job_id_uuid)
            assert cancelled_queued_job is not None
            assert cancelled_queued_job.status == JobStatus.cancelled
            assert cancelled_queued_job.assigned_worker_id is None

            running_worker_id = uuid4()
            running_job = Job(
                title="job-3",
                input_bundle_path="jobs/3/input/bundle.tar.gz",
                status=JobStatus.running,
                assigned_worker_id=running_worker_id,
            )
            session.add(running_job)
            await session.commit()
            await session.refresh(running_job)
            running_job_id = running_job.id

        cancel_running_response = await client.delete(f"/jobs/{running_job_id}", headers=headers)
        assert cancel_running_response.status_code == 409

        force_cancel_response = await client.delete(
            f"/jobs/{running_job_id}?force=true", headers=headers
        )
        assert force_cancel_response.status_code == 204

        history_response = await client.get(f"/jobs/{running_job_id}/history", headers=headers)
        assert history_response.status_code == 200
        history_events = history_response.json()["events"]
        cancel_requested_events = [
            event for event in history_events if event["event_type"] == "cancel_requested"
        ]
        assert len(cancel_requested_events) == 1
        assert cancel_requested_events[0]["worker_id"] == str(running_worker_id)

        async with get_sessionmaker()() as session:
            cancelled_running_job = await session.get(Job, running_job_id)
            assert cancelled_running_job is not None
            assert cancelled_running_job.status == JobStatus.cancelling
            assert cancelled_running_job.assigned_worker_id == running_worker_id


@pytest.mark.asyncio
async def test_list_jobs_uses_batched_history_load() -> None:
    headers = {"X-API-Token": "test-token"}

    async with app_client(make_settings()) as (_app, client):
        for index in range(3):
            create_response = await client.post(
                "/jobs",
                headers=headers,
                json={
                    "title": f"job-{index}",
                    "input_bundle_path": f"jobs/{index}/input/bundle.tar.gz",
                },
            )
            assert create_response.status_code == 200

        with (
            patch(
                "relaymd.orchestrator.routers.jobs_operator.load_job_history_events_for_jobs",
                new=AsyncMock(return_value={}),
            ) as batched_loader,
            patch(
                "relaymd.orchestrator.routers.jobs_operator.load_job_history_events",
                new=AsyncMock(return_value=[]),
            ) as single_loader,
        ):
            list_response = await client.get("/jobs", headers=headers)

        assert list_response.status_code == 200
        assert len(list_response.json()) == 3
        batched_loader.assert_awaited_once()
        single_loader.assert_not_called()


@pytest.mark.asyncio
async def test_requeue_creates_new_queued_job_with_checkpoint_fields() -> None:
    headers = {"X-API-Token": "test-token"}

    async with app_client(make_settings()) as (_app, client):
        register_response = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "NVIDIA A100",
                "gpu_count": 1,
                "vram_gb": 80,
            },
        )
        assert register_response.status_code == 200
        worker_id = register_response.json()["worker_id"]

        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={"title": "job-requeue", "input_bundle_path": "jobs/requeue/input/bundle.tar.gz"},
        )
        assert create_response.status_code == 200
        original_job = create_response.json()
        original_job_id = original_job["id"]

        request_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert request_response.status_code == 200
        assert request_response.json()["status"] == "assigned"
        assert request_response.json()["job_id"] == original_job_id

        checkpoint_response = await client.post(
            f"/jobs/{original_job_id}/checkpoint",
            headers=headers,
            json={"checkpoint_path": "jobs/requeue/checkpoints/latest"},
        )
        assert checkpoint_response.status_code == 204

        fail_response = await client.post(f"/jobs/{original_job_id}/fail", headers=headers)
        assert fail_response.status_code == 204

        requeue_response = await client.post(f"/jobs/{original_job_id}/requeue", headers=headers)
        assert requeue_response.status_code == 200
        requeued_job = requeue_response.json()

        assert requeued_job["id"] != original_job_id
        assert requeued_job["title"] == "job-requeue"
        assert requeued_job["status"] == "queued"
        assert requeued_job["input_bundle_path"] == "jobs/requeue/input/bundle.tar.gz"
        assert requeued_job["latest_checkpoint_path"] == "jobs/requeue/checkpoints/latest"
        assert requeued_job["last_checkpoint_at"] is not None
        assert requeued_job["assigned_worker_id"] is None


@pytest.mark.asyncio
async def test_requeue_missing_job_returns_404() -> None:
    headers = {"X-API-Token": "test-token"}

    async with app_client(make_settings()) as (_app, client):
        response = await client.post(
            "/jobs/00000000-0000-0000-0000-000000000000/requeue",
            headers=headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_job_accepts_caller_supplied_id() -> None:
    headers = {"X-API-Token": "test-token"}
    expected_id = "0b7edcb6-c482-4abf-9545-7c1a252ea0fd"
    async with app_client(make_settings()) as (_app, client):
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "id": expected_id,
                "title": "job-with-id",
                "input_bundle_path": "jobs/with-id/input/bundle.tar.gz",
            },
        )
        assert create_response.status_code == 200
        assert create_response.json()["id"] == expected_id


@pytest.mark.asyncio
async def test_create_job_persists_affinity_and_comment() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "affinity-job",
                "input_bundle_path": "jobs/affinity/input/bundle.tar.gz",
                "preferred_clusters": ["gilbreth", "anvil", "gilbreth"],
                "comment": "  pinned job comment  ",
            },
        )
        assert create_response.status_code == 200
        payload = create_response.json()
        assert payload["preferred_clusters"] == ["gilbreth", "anvil"]
        assert payload["comment"] == "pinned job comment"
        assert payload["queue_blocked_reason"] is None


@pytest.mark.asyncio
async def test_create_job_rejects_unknown_affinity_cluster() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "bad-affinity-job",
                "input_bundle_path": "jobs/affinity/input/bundle.tar.gz",
                "preferred_clusters": ["missing-cluster"],
            },
        )
        assert create_response.status_code == 422


@pytest.mark.asyncio
async def test_requeue_trims_preferred_clusters_for_blocked_reason() -> None:
    headers = {"X-API-Token": "test-token"}
    async with app_client(make_slurm_settings()) as (_app, client):
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "trim-requeue",
                "input_bundle_path": "jobs/trim/input/bundle.tar.gz",
            },
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["id"]

        async with get_sessionmaker()() as session:
            job = await session.get(Job, UUID(job_id))
            assert job is not None
            job.status = JobStatus.failed
            job.preferred_clusters_json = '[" gilbreth "]'
            session.add(job)
            await session.commit()

        requeue_response = await client.post(f"/jobs/{job_id}/requeue", headers=headers)
        assert requeue_response.status_code == 200
        payload = requeue_response.json()
        assert payload["preferred_clusters"] == ["gilbreth"]
        assert payload["queue_blocked_reason"] is None
