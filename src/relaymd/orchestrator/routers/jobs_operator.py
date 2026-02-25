from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobConflict, JobCreate, JobRead, JobStatus
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import JobTransitionConflictError, JobTransitionService

from ._responses import job_transition_conflict_response

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])


@router.post("", response_model=JobRead)
async def create_job(
    payload: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead:
    now = datetime.now(UTC).replace(tzinfo=None)
    job = Job(
        title=payload.title,
        input_bundle_path=payload.input_bundle_path,
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return JobRead.model_validate(job)


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
