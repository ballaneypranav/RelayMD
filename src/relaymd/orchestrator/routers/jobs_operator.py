from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobConflict, JobCreate, JobCreateConflict, JobRead, JobStatus
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import JobTransitionConflictError, JobTransitionService

from ._responses import job_transition_conflict_response

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])
logger = structlog.get_logger(__name__)


@router.post(
    "",
    response_model=JobRead,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobCreateConflict,
            "description": "Caller-provided job id already exists",
        }
    },
)
async def create_job(
    payload: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead | JSONResponse:
    now = datetime.now(UTC).replace(tzinfo=None)
    job = Job(
        id=payload.id if payload.id is not None else uuid4(),
        title=payload.title,
        input_bundle_path=payload.input_bundle_path,
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        if payload.id is not None:
            existing = await session.get(Job, payload.id)
            if existing is not None:
                conflict = JobCreateConflict(
                    message=f"Job with id {payload.id} already exists",
                    job_id=payload.id,
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=conflict.model_dump(mode="json"),
                )
        raise
    await session.refresh(job)
    logger.info(
        "job_created",
        job_id=str(job.id),
        title=job.title,
        input_bundle_path=job.input_bundle_path,
    )
    return JobRead.model_validate(job)


_TERMINAL_STATUSES = frozenset({JobStatus.completed, JobStatus.failed, JobStatus.cancelled})


_DEFAULT_PRUNE_STATUSES = [JobStatus.completed, JobStatus.failed, JobStatus.cancelled]


@router.delete("", status_code=status.HTTP_200_OK)
async def prune_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    job_status: Annotated[
        list[JobStatus],
        Query(alias="status", description="Terminal statuses to prune."),
    ] = _DEFAULT_PRUNE_STATUSES,
    older_than_days: Annotated[int, Query(ge=1)] = 30,
) -> dict[str, int]:
    """Hard-delete terminal-status jobs whose updated_at is older than N days."""
    non_terminal = [s for s in job_status if s not in _TERMINAL_STATUSES]
    if non_terminal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot prune active-status jobs: {[s.value for s in non_terminal]}",
        )
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than_days)
    jobs = (
        await session.exec(
            select(Job).where(
                col(Job.status).in_(job_status),
                col(Job.updated_at) < cutoff,
            )
        )
    ).all()
    for job in jobs:
        await session.delete(job)
    await session.commit()
    deleted = len(jobs)
    logger.info("jobs_pruned", count=deleted, older_than_days=older_than_days)
    return {"deleted": deleted}


@router.get("", response_model=list[JobRead])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[JobRead]:
    jobs = (await session.exec(select(Job).order_by(col(Job.created_at).desc()))).all()
    return [JobRead.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobRead.model_validate(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def cancel_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    force: bool = Query(default=False),
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == JobStatus.running and not force:
        return job_transition_conflict_response(
            JobTransitionConflictError(
                message="Running job requires force=true for cancellation",
                job_id=job.id,
                current_status=job.status,
                requested_status=JobStatus.cancelled,
            )
        )

    transitions = JobTransitionService()
    try:
        transitions.cancel_job(job)
    except JobTransitionConflictError as exc:
        return job_transition_conflict_response(exc)

    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{job_id}/requeue",
    response_model=JobRead,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": JobConflict,
            "description": "Job transition conflict",
        }
    },
)
async def requeue_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead | Response:
    existing_job = await session.get(Job, job_id)
    if existing_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    transitions = JobTransitionService()
    try:
        requeued_job = transitions.build_requeue_clone(existing_job)
    except JobTransitionConflictError as exc:
        return job_transition_conflict_response(exc)

    session.add(requeued_job)
    await session.commit()
    await session.refresh(requeued_job)
    return JobRead.model_validate(requeued_job)
