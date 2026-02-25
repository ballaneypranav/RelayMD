from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from relaymd.models import Job, JobCreate, JobRead, JobStatus
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    force: bool = Query(default=False),
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status == JobStatus.running and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Running job requires force=true for cancellation",
        )

    job.status = JobStatus.cancelled
    job.assigned_worker_id = None
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
