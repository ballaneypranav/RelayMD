from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from freezegun import freeze_time
from relaymd.models import Job, JobStatus, Platform, Worker

from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings, WorkerImageSource
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.scheduler import reap_stale_workers
from relaymd.orchestrator.services import worker_lifecycle_service

from ._worker_endpoints_test_helpers import app_client, make_settings


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
                    worker_image_key="atom-openmm",
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="train-2",
                    input_bundle_path="jobs/2/input/bundle.tar.gz",
                    worker_image_key="atom-openmm",
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
async def test_stale_worker_reaper_keeps_non_hpc_job_when_storage_status_fresh(
    monkeypatch,
) -> None:
    settings = make_settings()

    async def _fresh_status(self, *, storage, job_id):  # noqa: ARG001
        return True

    monkeypatch.setattr(
        worker_lifecycle_service.WorkerLifecycleService,
        "_status_is_fresh",
        _fresh_status,
    )

    async with app_client(settings) as (app, _client):
        with freeze_time("2026-01-01T12:00:00"):
            stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            async with get_sessionmaker()() as session:
                worker = Worker(
                    platform=Platform.salad,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=80,
                    worker_image_key="atom-openmm",
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="fresh-status",
                    input_bundle_path="jobs/fresh/input/bundle.tar.gz",
                    worker_image_key="atom-openmm",
                    status=JobStatus.running,
                    assigned_worker_id=worker.id,
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                job_id = job.id
                worker_id = worker.id

            stale_count = await reap_stale_workers(app.state.settings)
            assert stale_count == 0

            async with get_sessionmaker()() as session:
                kept_job = await session.get(Job, job_id)
                assert kept_job is not None
                assert kept_job.status == JobStatus.running
                kept_worker = await session.get(Worker, worker_id)
                assert kept_worker is not None


@pytest.mark.asyncio
async def test_stale_worker_reaper_keeps_hpc_job_when_slurm_running_and_status_stale(
    monkeypatch,
) -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="test-infisical",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                ssh_host="test-host",
                ssh_username="test-user",
                gpu_type="a100",
                gpu_count=1,
                worker_images={"atom-openmm": WorkerImageSource(sif_path="/shared/relaymd.sif")},
            )
        ],
    )

    async def _stale_status(self, *, storage, job_id):  # noqa: ARG001
        return False

    async def _slurm_live(*args, **kwargs):  # noqa: ARG001
        return {
            "12345": SimpleNamespace(
                provider_state="running",
                provider_state_raw="RUNNING",
                provider_reason=None,
            )
        }

    monkeypatch.setattr(
        worker_lifecycle_service.WorkerLifecycleService,
        "_status_is_fresh",
        _stale_status,
    )
    monkeypatch.setattr(worker_lifecycle_service, "_query_live_slurm_job_statuses", _slurm_live)

    async with app_client(settings) as (app, _client):
        with freeze_time("2026-01-01T12:00:00"):
            stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            async with get_sessionmaker()() as session:
                worker = Worker(
                    platform=Platform.hpc,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=80,
                    provider_id="gilbreth:12345",
                    worker_image_key="atom-openmm",
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="slurm-running",
                    input_bundle_path="jobs/slurm/input/bundle.tar.gz",
                    worker_image_key="atom-openmm",
                    status=JobStatus.running,
                    assigned_worker_id=worker.id,
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                job_id = job.id
                worker_id = worker.id

            stale_count = await reap_stale_workers(app.state.settings)
            assert stale_count == 0

            async with get_sessionmaker()() as session:
                kept_job = await session.get(Job, job_id)
                assert kept_job is not None
                assert kept_job.status == JobStatus.running
                kept_worker = await session.get(Worker, worker_id)
                assert kept_worker is not None


@pytest.mark.asyncio
async def test_stale_worker_reaper_requeues_hpc_job_when_slurm_not_running(
    monkeypatch,
) -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="test-infisical",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                ssh_host="test-host",
                ssh_username="test-user",
                gpu_type="a100",
                gpu_count=1,
                worker_images={"atom-openmm": WorkerImageSource(sif_path="/shared/relaymd.sif")},
            )
        ],
    )

    async def _stale_status(self, *, storage, job_id):  # noqa: ARG001
        return False

    async def _slurm_gone(*args, **kwargs):  # noqa: ARG001
        return {}

    monkeypatch.setattr(
        worker_lifecycle_service.WorkerLifecycleService,
        "_status_is_fresh",
        _stale_status,
    )
    monkeypatch.setattr(worker_lifecycle_service, "_query_live_slurm_job_statuses", _slurm_gone)

    async with app_client(settings) as (app, _client):
        with freeze_time("2026-01-01T12:00:00"):
            stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            async with get_sessionmaker()() as session:
                worker = Worker(
                    platform=Platform.hpc,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=80,
                    provider_id="gilbreth:12345",
                    worker_image_key="atom-openmm",
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="slurm-gone",
                    input_bundle_path="jobs/slurm-gone/input/bundle.tar.gz",
                    worker_image_key="atom-openmm",
                    status=JobStatus.running,
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
async def test_stale_worker_reaper_keeps_hpc_job_when_slurm_query_fails(
    monkeypatch,
) -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        database_url="sqlite+aiosqlite:///:memory:",
        api_token="test-token",
        infisical_token="test-infisical",
        slurm_cluster_configs=[
            ClusterConfig(
                name="gilbreth",
                partition="gpu",
                account="lab-account",
                ssh_host="test-host",
                ssh_username="test-user",
                gpu_type="a100",
                gpu_count=1,
                worker_images={"atom-openmm": WorkerImageSource(sif_path="/shared/relaymd.sif")},
            )
        ],
    )

    async def _stale_status(self, *, storage, job_id):  # noqa: ARG001
        return False

    async def _slurm_unknown(*args, **kwargs):  # noqa: ARG001
        return None

    monkeypatch.setattr(
        worker_lifecycle_service.WorkerLifecycleService,
        "_status_is_fresh",
        _stale_status,
    )
    monkeypatch.setattr(
        worker_lifecycle_service,
        "_query_live_slurm_job_statuses",
        _slurm_unknown,
    )

    async with app_client(settings) as (app, _client):
        with freeze_time("2026-01-01T12:00:00"):
            stale_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
            async with get_sessionmaker()() as session:
                worker = Worker(
                    platform=Platform.hpc,
                    gpu_model="A100",
                    gpu_count=1,
                    vram_gb=80,
                    provider_id="gilbreth:12345",
                    worker_image_key="atom-openmm",
                    last_heartbeat=stale_time,
                )
                session.add(worker)
                await session.commit()
                await session.refresh(worker)

                job = Job(
                    title="slurm-query-unknown",
                    input_bundle_path="jobs/slurm-unknown/input/bundle.tar.gz",
                    worker_image_key="atom-openmm",
                    status=JobStatus.running,
                    assigned_worker_id=worker.id,
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                job_id = job.id
                worker_id = worker.id

            stale_count = await reap_stale_workers(app.state.settings)
            assert stale_count == 0

            async with get_sessionmaker()() as session:
                kept_job = await session.get(Job, job_id)
                assert kept_job is not None
                assert kept_job.status == JobStatus.running
                kept_worker = await session.get(Worker, worker_id)
                assert kept_worker is not None
