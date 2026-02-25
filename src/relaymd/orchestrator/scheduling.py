from __future__ import annotations

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, Worker
from relaymd.orchestrator.services.assignment_service import AssignmentService, score_worker

__all__ = [
    "assign_job",
    "assign_job_for_requesting_worker",
    "score_worker",
]


async def assign_job_for_requesting_worker(
    session: AsyncSession,
    *,
    heartbeat_interval_seconds: int,
    requesting_worker_id: UUID,
    heartbeat_timeout_multiplier: float,
) -> Job | None:
    service = AssignmentService(
        session,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_timeout_multiplier=heartbeat_timeout_multiplier,
    )
    return await service.assign_job_for_requesting_worker(
        requesting_worker_id=requesting_worker_id,
    )


async def assign_job(
    session: AsyncSession,
    *,
    heartbeat_interval_seconds: int,
    heartbeat_timeout_multiplier: float,
) -> tuple[Job, Worker] | None:
    service = AssignmentService(
        session,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_timeout_multiplier=heartbeat_timeout_multiplier,
    )
    return await service.assign_next_job()
