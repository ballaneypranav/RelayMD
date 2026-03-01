from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Worker

from .job_transitions import JobTransitionService


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

        # Ensure worker is not stale
        stale_cutoff = self._stale_cutoff()
        if worker.last_heartbeat < stale_cutoff:
            return None

        # Ensure worker is not already busy
        busy_worker_ids = await self._busy_worker_ids()
        if worker.id in busy_worker_ids:
            return None

        queued_job = await self._claim_next_queued_job()
        if queued_job is None:
            return None

        self._transitions.assign_job(queued_job, worker_id=worker.id)
        self._session.add(queued_job)
        await self._session.commit()
        await self._session.refresh(queued_job)
        return queued_job

    async def assign_next_job(self) -> tuple[Job, Worker] | None:
        """Find the next queued job and assign it to the first available worker."""
        queued_job = await self._claim_next_queued_job()
        if queued_job is None:
            return None

        busy_worker_ids = await self._busy_worker_ids()
        stale_cutoff = self._stale_cutoff()

        # Find any fresh, non-placeholder worker that is not busy
        workers = (
            await self._session.exec(
                select(Worker)
                .where(
                    col(Worker.last_heartbeat) >= stale_cutoff,
                    # We ignore slurm_job_id because placeholders shouldn't receive assignments
                    # until they actually start and register.
                    col(Worker.slurm_job_id).is_(None),
                )
                .order_by(col(Worker.registered_at).asc())
            )
        ).all()

        available_workers = [w for w in workers if w.id not in busy_worker_ids]
        if not available_workers:
            return None

        selected_worker = available_workers[0]
        self._transitions.assign_job(queued_job, worker_id=selected_worker.id)
        self._session.add(queued_job)
        await self._session.commit()
        await self._session.refresh(queued_job)
        return queued_job, selected_worker
