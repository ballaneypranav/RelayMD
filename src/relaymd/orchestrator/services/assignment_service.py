from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import exists, update
from sqlalchemy.orm import aliased
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Worker, WorkerStatus

logger = structlog.get_logger(__name__)

CLAIM_RETRY_LIMIT = 3
ACTIVE_JOB_STATUSES = (JobStatus.assigned, JobStatus.running)


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

    def _stale_cutoff(self) -> datetime:
        timeout_seconds = self._heartbeat_timeout_multiplier * self._heartbeat_interval_seconds
        return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

    async def _busy_worker_ids(self) -> set[UUID]:
        busy_worker_ids = (
            await self._session.exec(
                select(Job.assigned_worker_id).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_(ACTIVE_JOB_STATUSES),
                )
            )
        ).all()
        return {worker_id for worker_id in busy_worker_ids if worker_id is not None}

    async def _is_worker_busy(self, worker_id: UUID) -> bool:
        return worker_id in await self._busy_worker_ids()

    async def _next_queued_job_id(self) -> UUID | None:
        return (
            await self._session.exec(
                select(Job.id)
                .where(Job.status == JobStatus.queued)
                .order_by(col(Job.created_at).asc())
                .limit(1)
            )
        ).first()

    async def _claim_queued_job(self, *, job_id: UUID, worker_id: UUID) -> Job | None:
        now = datetime.now(UTC).replace(tzinfo=None)
        busy_job = aliased(Job)
        worker_has_active_job = exists().where(
            col(busy_job.assigned_worker_id) == worker_id,
            col(busy_job.status).in_(ACTIVE_JOB_STATUSES),
        )
        result = await self._session.exec(
            update(Job)
            .where(
                col(Job.id) == job_id,
                col(Job.status) == JobStatus.queued,
                ~worker_has_active_job,
            )
            .values(
                status=JobStatus.assigned,
                assigned_worker_id=worker_id,
                assigned_at=now,
                status_changed_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            await self._session.rollback()
            return None

        await self._session.commit()
        return await self._session.get(Job, job_id)

    async def _claim_next_queued_job_for_worker(self, *, worker_id: UUID) -> Job | None:
        for _attempt in range(CLAIM_RETRY_LIMIT):
            job_id = await self._next_queued_job_id()
            if job_id is None:
                return None

            claimed_job = await self._claim_queued_job(job_id=job_id, worker_id=worker_id)
            if claimed_job is not None:
                return claimed_job

            if await self._is_worker_busy(worker_id):
                return None

        return None

    async def assign_job_for_requesting_worker(self, *, requesting_worker_id: UUID) -> Job | None:
        logger.info(
            "job_assignment_started",
            worker_id=str(requesting_worker_id),
            assignment_mode="requesting",
        )
        worker = await self._session.get(Worker, requesting_worker_id)
        if worker is None:
            return None
        worker_id = worker.id
        worker_provider_id = worker.provider_id

        # Ensure worker is not stale
        stale_cutoff = self._stale_cutoff()
        if worker.last_heartbeat < stale_cutoff:
            return None

        # Ensure worker is not already busy
        if await self._is_worker_busy(worker_id):
            return None

        queued_job = await self._claim_next_queued_job_for_worker(worker_id=worker_id)
        if queued_job is None:
            return None

        logger.info(
            "job_assignment_succeeded",
            assignment_mode="requesting",
            job_id=str(queued_job.id),
            worker_id=str(worker_id),
            provider_id=worker_provider_id,
        )
        return queued_job

    async def assign_next_job(self) -> tuple[Job, Worker] | None:
        """Find the next queued job and assign it to the first available worker."""
        queued_job_id = await self._next_queued_job_id()
        if queued_job_id is None:
            return None

        logger.info(
            "job_assignment_started", assignment_mode="scheduled", job_id=str(queued_job_id)
        )

        busy_worker_ids = await self._busy_worker_ids()
        stale_cutoff = self._stale_cutoff()

        # Find any fresh, non-placeholder worker that is not busy
        workers = (
            await self._session.exec(
                select(Worker)
                .where(
                    col(Worker.last_heartbeat) >= stale_cutoff,
                    # We only assign jobs to fully active workers; queued placeholders
                    # are ignored until they actually start and register.
                    Worker.status == WorkerStatus.active,
                )
                .order_by(col(Worker.registered_at).asc())
            )
        ).all()

        available_workers = [w for w in workers if w.id not in busy_worker_ids]
        if not available_workers:
            logger.info(
                "job_assignment_skipped_no_idle_workers",
                assignment_mode="scheduled",
                job_id=str(queued_job_id),
                busy_worker_count=len(busy_worker_ids),
                fresh_worker_count=len(workers),
            )
            return None

        queued_job: Job | None = None
        selected_worker: Worker | None = None
        for worker in available_workers:
            queued_job = await self._claim_next_queued_job_for_worker(worker_id=worker.id)
            if queued_job is not None:
                selected_worker = worker
                break

        if queued_job is None or selected_worker is None:
            return None

        logger.info(
            "job_assignment_succeeded",
            assignment_mode="scheduled",
            job_id=str(queued_job.id),
            worker_id=str(selected_worker.id),
            provider_id=selected_worker.provider_id,
        )
        return queued_job, selected_worker
