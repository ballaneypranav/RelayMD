from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Worker, WorkerRegister, WorkerStatus

from .job_transitions import JobTransitionService

logger = structlog.get_logger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WorkerLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transitions = JobTransitionService()

    async def register_worker(self, payload: WorkerRegister) -> Worker:
        """Register a worker, activating an existing queued placeholder if one matches.

        When a SLURM-launched worker starts, it passes ``provider_id`` (composed
        from ``RELAYMD_CLUSTER_NAME`` + ``SLURM_JOB_ID`` in the sbatch environment).
        If a queued placeholder with that exact ``provider_id`` exists, we activate
        it in-place — updating the real VRAM, heartbeat, and status — so the same
        UUID represents the worker across its entire lifecycle, from submission to
        completion. This avoids orphaned placeholder rows without requiring a
        sentinel-based string encoding.

        If no matching placeholder is found (Salad workers, or a SLURM worker whose
        placeholder was already reaped), a fresh row is inserted.
        """
        if payload.provider_id:
            existing = (
                await self._session.exec(
                    select(Worker).where(
                        Worker.provider_id == payload.provider_id,
                        Worker.status == WorkerStatus.queued,
                    )
                )
            ).first()
            if existing is not None:
                logger.info(
                    "queued_placeholder_activated",
                    provider_id=payload.provider_id,
                    worker_id=str(existing.id),
                    platform=str(payload.platform),
                )
                existing.status = WorkerStatus.active
                existing.vram_gb = payload.vram_gb
                existing.gpu_model = payload.gpu_model
                existing.gpu_count = payload.gpu_count
                existing.last_heartbeat = _utcnow_naive()
                existing.provider_state = None
                existing.provider_state_raw = None
                existing.provider_reason = None
                existing.provider_last_checked_at = None
                self._session.add(existing)
                await self._session.commit()
                await self._session.refresh(existing)
                return existing

        worker = Worker(
            platform=payload.platform,
            gpu_model=payload.gpu_model,
            gpu_count=payload.gpu_count,
            vram_gb=payload.vram_gb,
            provider_id=payload.provider_id,
            status=WorkerStatus.active,
        )
        self._session.add(worker)
        await self._session.commit()
        await self._session.refresh(worker)
        logger.info(
            "worker_registered",
            worker_id=str(worker.id),
            provider_id=worker.provider_id,
            platform=str(worker.platform),
        )
        return worker

    async def heartbeat(self, worker_id: UUID) -> Worker | None:
        worker = await self._session.get(Worker, worker_id)
        if worker is None:
            return None

        worker.last_heartbeat = _utcnow_naive()
        self._session.add(worker)
        await self._session.commit()
        return worker

    async def deregister(self, worker_id: UUID) -> bool:
        worker = await self._session.get(Worker, worker_id)
        if worker is None:
            return False

        jobs = (
            await self._session.exec(
                select(Job).where(
                    Job.assigned_worker_id == worker_id,
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()
        for job in jobs:
            self._transitions.requeue_in_place(job)
            self._session.add(job)

        await self._session.delete(worker)
        await self._session.commit()
        return True

    async def reap_stale_workers(self, *, stale_cutoff: datetime) -> int:
        stale_workers = (
            await self._session.exec(
                select(Worker).where(
                    col(Worker.last_heartbeat) < stale_cutoff,
                    # Only reap active workers — queued placeholders are managed
                    # by reap_dead_slurm_placeholders via squeue.
                    Worker.status == WorkerStatus.active,
                )
            )
        ).all()
        if not stale_workers:
            await self._session.commit()
            return 0

        stale_worker_ids = [worker.id for worker in stale_workers]
        jobs_to_requeue = (
            await self._session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).in_(stale_worker_ids),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()
        for job in jobs_to_requeue:
            self._transitions.requeue_in_place(job)
            self._session.add(job)

        for worker in stale_workers:
            await self._session.delete(worker)

        await self._session.commit()
        return len(stale_workers)

    async def requeue_orphaned_jobs_once(self) -> int:
        worker_ids = set((await self._session.exec(select(Worker.id))).all())
        assigned_jobs = (
            await self._session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()

        requeued_count = 0
        for job in assigned_jobs:
            if job.assigned_worker_id not in worker_ids:
                self._transitions.requeue_in_place(job)
                self._session.add(job)
                requeued_count += 1

        if requeued_count > 0:
            await self._session.commit()
            return requeued_count

        await self._session.rollback()
        return 0
