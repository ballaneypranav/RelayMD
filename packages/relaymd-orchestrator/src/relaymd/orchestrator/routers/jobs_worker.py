from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from relaymd.models import CheckpointReport, Job, JobAssigned, JobStatus, NoJobAvailable
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.scheduler import assign_job
from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])


@router.post("/request", response_model=JobAssigned | NoJobAvailable)
async def request_job(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobAssigned | NoJobAvailable:
    assignment = await assign_job(session)
    if assignment is None:
        return NoJobAvailable()

    job, _worker = assignment
    return JobAssigned(
        job_id=job.id,
        input_bundle_path=job.input_bundle_path,
        latest_checkpoint_path=job.latest_checkpoint_path,
    )


@router.post("/{job_id}/checkpoint", status_code=status.HTTP_204_NO_CONTENT)
async def report_checkpoint(
    job_id: UUID,
    payload: CheckpointReport,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    now = datetime.now(UTC).replace(tzinfo=None)
    job.latest_checkpoint_path = payload.checkpoint_path
    job.last_checkpoint_at = now
    job.updated_at = now
    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = JobStatus.completed
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
async def fail_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = JobStatus.failed
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
