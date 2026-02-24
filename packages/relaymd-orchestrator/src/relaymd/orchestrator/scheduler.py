from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from relaymd.models import Job, JobStatus, Platform, Worker
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from sqlalchemy import Select
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

HEARTBEAT_INTERVAL_SECONDS = 30


def score_worker(worker: Worker) -> int:
    platform_bonus = 10 if worker.platform == Platform.hpc else 0
    return worker.gpu_count * 1000 + platform_bonus * 100 + worker.vram_gb


async def assign_job(session: AsyncSession) -> tuple[Job, Worker] | None:
    queued_job_statement: Select[tuple[Job]] = (
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(col(Job.created_at).asc())
        .limit(1)
    )
    queued_job = (await session.exec(queued_job_statement)).first()
    if queued_job is None:
        return None

    busy_worker_ids = (
        await session.exec(
            select(Job.assigned_worker_id).where(
                col(Job.assigned_worker_id).is_not(None),
                col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
            )
        )
    ).all()
    busy_worker_id_set = {worker_id for worker_id in busy_worker_ids if worker_id is not None}

    all_workers = (await session.exec(select(Worker))).all()
    idle_workers = [worker for worker in all_workers if worker.id not in busy_worker_id_set]
    if not idle_workers:
        return None

    selected_worker = max(
        idle_workers,
        key=lambda worker: (score_worker(worker), worker.registered_at.timestamp() * -1),
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    queued_job.assigned_worker_id = selected_worker.id
    queued_job.status = JobStatus.assigned
    queued_job.updated_at = now

    session.add(queued_job)
    await session.commit()
    await session.refresh(queued_job)

    return queued_job, selected_worker


async def reap_stale_workers(settings: OrchestratorSettings) -> int:
    sessionmaker = get_sessionmaker()
    timeout_seconds = settings.heartbeat_timeout_multiplier * HEARTBEAT_INTERVAL_SECONDS
    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

    async with sessionmaker() as session:
        stale_workers = (
            await session.exec(select(Worker).where(col(Worker.last_heartbeat) < stale_cutoff))
        ).all()
        if not stale_workers:
            await session.commit()
            return 0

        stale_worker_ids = [worker.id for worker in stale_workers]
        jobs_to_requeue = (
            await session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).in_(stale_worker_ids),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()

        now = datetime.now(UTC).replace(tzinfo=None)
        for job in jobs_to_requeue:
            job.status = JobStatus.queued
            job.assigned_worker_id = None
            job.updated_at = now
            session.add(job)

        for worker in stale_workers:
            await session.delete(worker)

        await session.commit()
        return len(stale_workers)


async def stale_worker_reaper_loop(
    settings: OrchestratorSettings,
    stop_event: asyncio.Event,
    interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    while not stop_event.is_set():
        await reap_stale_workers(settings)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


async def orphaned_job_requeue_loop(
    stop_event: asyncio.Event,
    interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    sessionmaker = get_sessionmaker()
    while not stop_event.is_set():
        async with sessionmaker() as session:
            worker_ids = set((await session.exec(select(Worker.id))).all())
            assigned_jobs = (
                await session.exec(
                    select(Job).where(
                        col(Job.assigned_worker_id).is_not(None),
                        col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                    )
                )
            ).all()

            now = datetime.now(UTC).replace(tzinfo=None)
            changed = False
            for job in assigned_jobs:
                if job.assigned_worker_id not in worker_ids:
                    job.status = JobStatus.queued
                    job.assigned_worker_id = None
                    job.updated_at = now
                    session.add(job)
                    changed = True

            if changed:
                await session.commit()
            else:
                await session.rollback()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
