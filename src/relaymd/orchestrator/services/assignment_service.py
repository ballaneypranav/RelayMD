from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Platform, Worker

from .job_transitions import JobTransitionService

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


class AssignmentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        heartbeat_interval_seconds: int,
        heartbeat_timeout_multiplier: float,
    ) -> None:
        self._session = session
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_timeout_multiplier = heartbeat_timeout_multiplier
        self._transitions = JobTransitionService()

    def _stale_cutoff(self) -> datetime:
        timeout_seconds = self._heartbeat_timeout_multiplier * self._heartbeat_interval_seconds
        return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

    async def _busy_worker_ids(self) -> set[UUID]:
        busy_worker_ids = (
            await self._session.exec(
                select(Job.assigned_worker_id).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()
        return {worker_id for worker_id in busy_worker_ids if worker_id is not None}

    async def _claim_next_queued_job(self) -> Job | None:
        return (
            await self._session.exec(
                select(Job)
                .where(Job.status == JobStatus.queued)
                .order_by(col(Job.created_at).asc())
                .limit(1)
                .with_for_update()
            )
        ).first()

    async def assign_job_for_requesting_worker(self, *, requesting_worker_id: UUID) -> Job | None:
        worker = await self._session.get(Worker, requesting_worker_id)
        if worker is None:
            return None

        stale_cutoff = self._stale_cutoff()
        if worker.last_heartbeat < stale_cutoff:
            return None

        queued_job = await self._claim_next_queued_job()
        if queued_job is None:
            return None

        busy_worker_ids = await self._busy_worker_ids()
        fresh_workers = (
            await self._session.exec(
                select(Worker).where(
                    col(Worker.last_heartbeat) >= stale_cutoff,
                    col(Worker.slurm_job_id).is_(None),
                )
            )
        ).all()
        idle_workers = [
            candidate for candidate in fresh_workers if candidate.id not in busy_worker_ids
        ]
        if not idle_workers:
            return None

        selected_worker = max(
            idle_workers,
            key=lambda candidate: (
                score_worker(candidate),
                candidate.registered_at.timestamp() * -1,
            ),
        )
        if selected_worker.id != requesting_worker_id:
            return None

        self._transitions.assign_job(queued_job, worker_id=selected_worker.id)
        self._session.add(queued_job)
        await self._session.commit()
        await self._session.refresh(queued_job)
        return queued_job

    async def assign_next_job(self) -> tuple[Job, Worker] | None:
        queued_job = await self._claim_next_queued_job()
        if queued_job is None:
            return None

        busy_worker_ids = await self._busy_worker_ids()
        all_workers = (
            await self._session.exec(select(Worker).where(col(Worker.slurm_job_id).is_(None)))
        ).all()
        idle_workers = [worker for worker in all_workers if worker.id not in busy_worker_ids]
        if not idle_workers:
            return None

        selected_worker = max(
            idle_workers,
            key=lambda worker: (score_worker(worker), worker.registered_at.timestamp() * -1),
        )
        self._transitions.assign_job(queued_job, worker_id=selected_worker.id)
        self._session.add(queued_job)
        await self._session.commit()
        await self._session.refresh(queued_job)
        return queued_job, selected_worker
