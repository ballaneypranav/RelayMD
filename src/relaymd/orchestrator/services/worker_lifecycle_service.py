from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Worker, WorkerRegister

from .job_transitions import JobTransitionService


class WorkerLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transitions = JobTransitionService()

    async def register_worker(self, payload: WorkerRegister) -> Worker:
        worker = Worker(**payload.model_dump())
        self._session.add(worker)
        await self._session.commit()
        await self._session.refresh(worker)
        return worker

    async def heartbeat(self, worker_id: UUID) -> Worker | None:
        worker = await self._session.get(Worker, worker_id)
        if worker is None:
            return None

        worker.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)
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
                select(Worker).where(col(Worker.last_heartbeat) < stale_cutoff)
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
