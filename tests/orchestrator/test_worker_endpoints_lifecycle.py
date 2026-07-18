from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from relaymd.models import Job, JobStatus

from relaymd.orchestrator.db import get_sessionmaker

from ._worker_endpoints_test_helpers import app_client, make_settings


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
                "worker_image_key": "atom-openmm",
            },
        )
        assert register_response.status_code == 200
        worker_id = register_response.json()["worker_id"]

        async with get_sessionmaker()() as session:
            job = Job(
                title="train-1",
                input_bundle_path="jobs/1/input/bundle.tar.gz",
                worker_image_key="atom-openmm",
            )
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
        assert request_response.json()["latest_checkpoint_manifest_path"] is None

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
            assert db_job.latest_checkpoint_manifest_path == "jobs/1/checkpoints/latest"
            assert db_job.last_checkpoint_at is not None


@pytest.mark.asyncio
async def test_heartbeat_progress_updates_only_assigned_worker_job() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        worker_one_response = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "A100",
                "gpu_count": 2,
                "vram_gb": 80,
                "worker_image_key": "atom-openmm",
            },
        )
        worker_one_id = worker_one_response.json()["worker_id"]
        worker_two_response = await client.post(
            "/workers/register",
            headers=headers,
            json={
                "platform": "hpc",
                "gpu_model": "A100",
                "gpu_count": 2,
                "vram_gb": 80,
                "worker_image_key": "atom-openmm",
            },
        )
        worker_two_id = worker_two_response.json()["worker_id"]

        async with get_sessionmaker()() as session:
            job = Job(
                title="train-1",
                input_bundle_path="jobs/1/input/bundle.tar.gz",
                worker_image_key="atom-openmm",
                status=JobStatus.running,
                assigned_worker_id=UUID(worker_one_id),
                progress=0.25,
                progress_codes_json='["progress_missing"]',
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = job.id

        heartbeat_response = await client.post(
            f"/workers/{worker_two_id}/heartbeat",
            headers=headers,
            json={"job_id": str(job_id), "progress": 0.9, "progress_codes": ["progress_empty"]},
        )
        assert heartbeat_response.status_code == 204

        async with get_sessionmaker()() as session:
            db_job = await session.get(Job, job_id)
            assert db_job is not None
            assert db_job.progress == 0.25
            assert db_job.progress_codes_json == '["progress_missing"]'


@pytest.mark.asyncio
async def test_worker_start_lifecycle_and_checkpoint_timestamps() -> None:
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
                "worker_image_key": "atom-openmm",
            },
        )
        worker_id = register_response.json()["worker_id"]
        create_response = await client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "train-lifecycle",
                "input_bundle_path": "jobs/lifecycle/input/bundle.tar.gz",
            },
        )
        job_id = UUID(create_response.json()["id"])

        await asyncio.sleep(0.001)
        request_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert request_response.status_code == 200
        assert request_response.json()["status"] == "assigned"

        async with get_sessionmaker()() as session:
            assigned_job = await session.get(Job, job_id)
            assert assigned_job is not None
            assert assigned_job.status == JobStatus.assigned
            assert assigned_job.assigned_at is not None
            assert assigned_job.started_at is None
            assert assigned_job.status_changed_at == assigned_job.assigned_at

        await asyncio.sleep(0.001)
        start_response = await client.post(f"/jobs/{job_id}/start", headers=headers)
        assert start_response.status_code == 204

        async with get_sessionmaker()() as session:
            running_job = await session.get(Job, job_id)
            assert running_job is not None
            assert running_job.status == JobStatus.running
            assert running_job.started_at is not None
            assert running_job.status_changed_at == running_job.started_at
            started_at = running_job.started_at
            running_status_changed_at = running_job.status_changed_at

        await asyncio.sleep(0.001)
        start_again_response = await client.post(f"/jobs/{job_id}/start", headers=headers)
        assert start_again_response.status_code == 204

        async with get_sessionmaker()() as session:
            still_running_job = await session.get(Job, job_id)
            assert still_running_job is not None
            assert still_running_job.started_at == started_at
            assert still_running_job.status_changed_at == running_status_changed_at

        await asyncio.sleep(0.001)
        checkpoint_response = await client.post(
            f"/jobs/{job_id}/checkpoint",
            headers=headers,
            json={"checkpoint_path": "jobs/lifecycle/checkpoints/latest"},
        )
        assert checkpoint_response.status_code == 204

        async with get_sessionmaker()() as session:
            checkpointed_job = await session.get(Job, job_id)
            assert checkpointed_job is not None
            assert checkpointed_job.last_checkpoint_at is not None
            assert checkpointed_job.updated_at == checkpointed_job.last_checkpoint_at
            assert checkpointed_job.status_changed_at == running_status_changed_at

        await asyncio.sleep(0.001)
        complete_response = await client.post(f"/jobs/{job_id}/complete", headers=headers)
        assert complete_response.status_code == 204

        async with get_sessionmaker()() as session:
            completed_job = await session.get(Job, job_id)
            assert completed_job is not None
            assert completed_job.status == JobStatus.completed
            assert completed_job.status_changed_at > running_status_changed_at
            assert completed_job.updated_at == completed_job.status_changed_at


@pytest.mark.asyncio
async def test_checkpoint_history_payload_includes_only_supplied_optional_fields() -> None:
    settings = make_settings()
    headers = {"X-API-Token": "test-token"}

    async with app_client(settings) as (_app, client):
        worker_id = (
            await client.post(
                "/workers/register",
                headers=headers,
                json={
                    "platform": "hpc",
                    "gpu_model": "A100",
                    "gpu_count": 1,
                    "vram_gb": 80,
                    "worker_image_key": "atom-openmm",
                },
            )
        ).json()["worker_id"]
        job_id = (
            await client.post(
                "/jobs",
                headers=headers,
                json={
                    "title": "checkpoint-fields",
                    "input_bundle_path": "jobs/cp/input/bundle.tar.gz",
                },
            )
        ).json()["id"]
        request_response = await client.post(
            "/jobs/request",
            headers=headers,
            params={"worker_id": worker_id},
        )
        assert request_response.status_code == 200

        checkpoint_response = await client.post(
            f"/jobs/{job_id}/checkpoint",
            headers=headers,
            json={"checkpoint_path": "jobs/cp/checkpoints/latest", "progress": 0.75},
        )
        assert checkpoint_response.status_code == 204

        history_response = await client.get(f"/jobs/{job_id}/history", headers=headers)
        assert history_response.status_code == 200
        checkpoint_events = [
            event
            for event in history_response.json()["events"]
            if event["event_type"] == "checkpoint"
        ]
        assert len(checkpoint_events) == 1
        assert checkpoint_events[0]["payload"] == {
            "checkpoint_manifest_path": "jobs/cp/checkpoints/latest",
            "checkpoint_path": "jobs/cp/checkpoints/latest",
            "progress": 0.75,
        }
