from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from relaymd.models import Job, JobStatus, Platform, Worker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.orchestrator.services.assignment_service import AssignmentService


@asynccontextmanager
async def _sessionmaker(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assignment.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


def _worker(*, gpu_model: str) -> Worker:
    return Worker(
        platform=Platform.hpc,
        gpu_model=gpu_model,
        gpu_count=1,
        vram_gb=80,
        last_heartbeat=datetime.now(UTC).replace(tzinfo=None),
    )


def _job(*, title: str) -> Job:
    return Job(title=title, input_bundle_path=f"jobs/{title}/input/bundle.tar.gz")


async def _assign(
    maker: async_sessionmaker[AsyncSession],
    *,
    worker_id,
) -> Job | None:
    async with maker() as session:
        return await AssignmentService(
            session,
            heartbeat_interval_seconds=10,
            heartbeat_timeout_multiplier=3,
        ).assign_job_for_requesting_worker(requesting_worker_id=worker_id)


async def _assign_next(
    maker: async_sessionmaker[AsyncSession],
) -> tuple[Job, Worker] | None:
    async with maker() as session:
        return await AssignmentService(
            session,
            heartbeat_interval_seconds=10,
            heartbeat_timeout_multiplier=3,
        ).assign_next_job()


@pytest.mark.asyncio
async def test_concurrent_workers_cannot_claim_same_queued_job(tmp_path: Path) -> None:
    async with _sessionmaker(tmp_path) as maker:
        async with maker() as session:
            worker_1 = _worker(gpu_model="A30")
            worker_2 = _worker(gpu_model="A100")
            job = _job(title="single")
            session.add_all([worker_1, worker_2, job])
            await session.commit()
            await session.refresh(worker_1)
            await session.refresh(worker_2)
            await session.refresh(job)

            worker_ids = [worker_1.id, worker_2.id]
            job_id = job.id

        results = await asyncio.gather(
            *(_assign(maker, worker_id=worker_id) for worker_id in worker_ids)
        )

        assigned_jobs = [job for job in results if job is not None]
        assert len(assigned_jobs) == 1
        assert assigned_jobs[0].id == job_id
        assert results.count(None) == 1

        async with maker() as session:
            db_job = await session.get(Job, job_id)
            assert db_job is not None
            assert db_job.status == JobStatus.assigned
            assert db_job.assigned_worker_id in worker_ids


@pytest.mark.asyncio
async def test_concurrent_workers_claim_distinct_queued_jobs(tmp_path: Path) -> None:
    async with _sessionmaker(tmp_path) as maker:
        async with maker() as session:
            worker_1 = _worker(gpu_model="A30")
            worker_2 = _worker(gpu_model="A100")
            job_1 = _job(title="first")
            job_2 = _job(title="second")
            session.add_all([worker_1, worker_2, job_1, job_2])
            await session.commit()
            await session.refresh(worker_1)
            await session.refresh(worker_2)
            await session.refresh(job_1)
            await session.refresh(job_2)

            worker_ids = {worker_1.id, worker_2.id}
            job_ids = {job_1.id, job_2.id}

        results = await asyncio.gather(
            *(_assign(maker, worker_id=worker_id) for worker_id in worker_ids)
        )

        assert {job.id for job in results if job is not None} == job_ids
        assert all(job is not None for job in results)

        async with maker() as session:
            db_jobs = (await session.exec(select(Job).order_by(col(Job.created_at)))).all()
            assert {job.id for job in db_jobs} == job_ids
            assert {job.status for job in db_jobs} == {JobStatus.assigned}
            assert {job.assigned_worker_id for job in db_jobs} == worker_ids


@pytest.mark.asyncio
async def test_concurrent_requests_from_same_worker_claim_only_one_job(tmp_path: Path) -> None:
    async with _sessionmaker(tmp_path) as maker:
        async with maker() as session:
            worker = _worker(gpu_model="A100")
            job_1 = _job(title="first")
            job_2 = _job(title="second")
            session.add_all([worker, job_1, job_2])
            await session.commit()
            await session.refresh(worker)
            await session.refresh(job_1)
            await session.refresh(job_2)

            worker_id = worker.id
            job_ids = {job_1.id, job_2.id}

        results = await asyncio.gather(
            _assign(maker, worker_id=worker_id),
            _assign(maker, worker_id=worker_id),
        )

        assigned_jobs = [job for job in results if job is not None]
        assert len(assigned_jobs) == 1
        assert results.count(None) == 1

        async with maker() as session:
            db_jobs = (await session.exec(select(Job).order_by(col(Job.created_at)))).all()
            assigned = [job for job in db_jobs if job.status == JobStatus.assigned]
            queued = [job for job in db_jobs if job.status == JobStatus.queued]

        assert len(assigned) == 1
        assert assigned[0].id in job_ids
        assert assigned[0].assigned_worker_id == worker_id
        assert len(queued) == 1


@pytest.mark.asyncio
async def test_worker_only_claims_job_matching_pinned_cluster(tmp_path: Path) -> None:
    async with _sessionmaker(tmp_path) as maker:
        async with maker() as session:
            worker = _worker(gpu_model="A100")
            worker.provider_id = "gilbreth:12345"
            pinned_job = _job(title="pinned")
            pinned_job.preferred_clusters_json = '["anvil"]'
            unpinned_job = _job(title="unpinned")
            session.add_all([worker, pinned_job, unpinned_job])
            await session.commit()
            await session.refresh(worker)

            worker_id = worker.id
            pinned_job_id = pinned_job.id
            unpinned_job_id = unpinned_job.id

        claimed = await _assign(maker, worker_id=worker_id)
        assert claimed is not None
        assert claimed.id == unpinned_job_id

        async with maker() as session:
            pinned = await session.get(Job, pinned_job_id)
            assert pinned is not None
            assert pinned.status == JobStatus.queued


@pytest.mark.asyncio
async def test_assign_next_job_respects_cluster_pinning_across_workers(tmp_path: Path) -> None:
    async with _sessionmaker(tmp_path) as maker:
        async with maker() as session:
            worker_1 = _worker(gpu_model="A100")
            worker_1.provider_id = "gilbreth:11111"
            worker_2 = _worker(gpu_model="A100")
            worker_2.provider_id = "anvil:22222"
            pinned_job = _job(title="anvil-pinned")
            pinned_job.preferred_clusters_json = '["anvil"]'
            session.add_all([worker_1, worker_2, pinned_job])
            await session.commit()
            await session.refresh(worker_2)
            pinned_job_id = pinned_job.id
            expected_worker_id = worker_2.id

        assignment = await _assign_next(maker)
        assert assignment is not None
        assigned_job, selected_worker = assignment
        assert assigned_job.id == pinned_job_id
        assert selected_worker.id == expected_worker_id
