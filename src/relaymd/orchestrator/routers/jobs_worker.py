from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import (
    CheckpointReport,
    Job,
    JobAssigned,
    JobConflict,
    NoJobAvailable,
)
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import (
    AssignmentService,
    JobTransitionConflictError,
    JobTransitionService,
)

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])


def _get_settings(request: Request) -> OrchestratorSettings:
    return request.app.state.settings


def _conflict_response(exc: JobTransitionConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=exc.to_response_model().model_dump(mode="json"),
    )


@router.post("/request", response_model=JobAssigned | NoJobAvailable)
async def request_job(
    worker_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[OrchestratorSettings, Depends(_get_settings)],
) -> JobAssigned | NoJobAvailable:
    assigned_job = await AssignmentService(
        session,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        heartbeat_timeout_multiplier=settings.heartbeat_timeout_multiplier,
    ).assign_job_for_requesting_worker(
        requesting_worker_id=worker_id,
    )
    if assigned_job is None:
        return NoJobAvailable()

    return JobAssigned(
        job_id=assigned_job.id,
        input_bundle_path=assigned_job.input_bundle_path,
        latest_checkpoint_path=assigned_job.latest_checkpoint_path,
    )


@router.post(
    "/{job_id}/checkpoint",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def report_checkpoint(
    job_id: UUID,
    payload: CheckpointReport,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    transitions = JobTransitionService()
    try:
        transitions.report_checkpoint(job, checkpoint_path=payload.checkpoint_path)
    except JobTransitionConflictError as exc:
        return _conflict_response(exc)

    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{job_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def complete_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    transitions = JobTransitionService()
    try:
        transitions.mark_job_completed(job)
    except JobTransitionConflictError as exc:
        return _conflict_response(exc)

    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{job_id}/fail",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def fail_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    transitions = JobTransitionService()
    try:
        transitions.mark_job_failed(job)
    except JobTransitionConflictError as exc:
        return _conflict_response(exc)

    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
