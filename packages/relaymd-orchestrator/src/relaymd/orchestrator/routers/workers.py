from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from relaymd.models import Job, JobStatus, Worker, WorkerRead, WorkerRegister
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/workers", dependencies=[Depends(require_worker_api_token)])


@router.get("", response_model=list[WorkerRead])
async def list_workers(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WorkerRead]:
    workers = (await session.exec(select(Worker).order_by(col(Worker.registered_at).desc()))).all()
    return [WorkerRead.model_validate(worker) for worker in workers]


@router.post("/register")
async def register_worker(
    payload: WorkerRegister,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, UUID]:
    worker = Worker(**payload.model_dump())
    session.add(worker)
    await session.commit()
    await session.refresh(worker)
    return {"worker_id": worker.id}


@router.post("/{worker_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat_worker(
    worker_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    worker = await session.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    worker.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)
    session.add(worker)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{worker_id}/deregister", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_worker(
    worker_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    worker = await session.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    jobs = (
        await session.exec(
            select(Job).where(
                Job.assigned_worker_id == worker_id,
                col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
            )
        )
    ).all()
    now = datetime.now(UTC).replace(tzinfo=None)
    for job in jobs:
        job.status = JobStatus.queued
        job.assigned_worker_id = None
        job.updated_at = now
        session.add(job)

    await session.delete(worker)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
