from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import JobConflict, Worker, WorkerRead, WorkerRegister
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import JobTransitionConflictError, WorkerLifecycleService

from ._responses import job_transition_conflict_response

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
    worker = await WorkerLifecycleService(session).register_worker(payload)
    return {"worker_id": worker.id}


@router.post("/{worker_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat_worker(
    worker_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    worker = await WorkerLifecycleService(session).heartbeat(worker_id)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{worker_id}/deregister",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def deregister_worker(
    worker_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    try:
        removed = await WorkerLifecycleService(session).deregister(worker_id)
    except JobTransitionConflictError as exc:
        return job_transition_conflict_response(exc)

    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
