from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from relaymd.models import Job, JobStatus, Platform, Worker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

HEARTBEAT_INTERVAL_SECONDS = 30

# GPU model strings observed/expected across HPC and Salad deployments.
VRAM_TIERS: dict[str, int] = {
    "NVIDIA H100": 94,
    "NVIDIA A100": 80,
    "NVIDIA A6000": 48,
    "NVIDIA RTX A6000": 48,
    "NVIDIA A5000": 24,
    "NVIDIA RTX A5000": 24,
    "NVIDIA RTX 4090": 24,
    "NVIDIA A10": 24,
}


def _resolved_vram_gb(worker: Worker) -> int:
    if worker.vram_gb > 0:
        return worker.vram_gb
    return VRAM_TIERS.get(worker.gpu_model.strip(), 0)


def score_worker(worker: Worker) -> int:
    platform_bonus = 10 if worker.platform == Platform.hpc else 0
    return worker.gpu_count * 1000 + platform_bonus * 100 + _resolved_vram_gb(worker)


async def assign_job_for_requesting_worker(
    session: AsyncSession,
    *,
    requesting_worker_id: UUID,
    heartbeat_timeout_multiplier: float,
) -> Job | None:
    worker = await session.get(Worker, requesting_worker_id)
    if worker is None:
        return None

    timeout_seconds = heartbeat_timeout_multiplier * HEARTBEAT_INTERVAL_SECONDS
    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)
    if worker.last_heartbeat < stale_cutoff:
        return None

    queued_job = (
        await session.exec(
            select(Job)
            .where(Job.status == JobStatus.queued)
            .order_by(col(Job.created_at).asc())
            .limit(1)
        )
    ).first()
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

    idle_workers = (
        await session.exec(select(Worker).where(col(Worker.last_heartbeat) >= stale_cutoff))
    ).all()
    idle_workers = [
        idle_worker for idle_worker in idle_workers if idle_worker.id not in busy_worker_id_set
    ]
    if not idle_workers:
        return None

    selected_worker = max(
        idle_workers,
        key=lambda idle_worker: (
            score_worker(idle_worker),
            idle_worker.registered_at.timestamp() * -1,
        ),
    )
    if selected_worker.id != requesting_worker_id:
        return None

    now = datetime.now(UTC).replace(tzinfo=None)
    queued_job.assigned_worker_id = selected_worker.id
    queued_job.status = JobStatus.assigned
    queued_job.updated_at = now

    session.add(queued_job)
    await session.commit()
    await session.refresh(queued_job)
    return queued_job
