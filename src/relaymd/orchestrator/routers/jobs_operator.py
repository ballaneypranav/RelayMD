from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobConflict, JobCreate, JobCreateConflict, JobRead, JobStatus
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import JobTransitionConflictError, JobTransitionService

from ._responses import job_transition_conflict_response

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])
logger = structlog.get_logger(__name__)


def _job_to_read(job: Job) -> JobRead:
    progress_codes: list[str] = []
    checkpoint_cycle_failures: list[dict[str, str]] = []
    if job.progress_codes_json:
        try:
            parsed_codes = json.loads(job.progress_codes_json)
            if isinstance(parsed_codes, list):
                progress_codes = [str(item) for item in parsed_codes]
        except Exception:
            progress_codes = []
    if job.checkpoint_cycle_failures_json:
        try:
            parsed_failures = json.loads(job.checkpoint_cycle_failures_json)
            if isinstance(parsed_failures, list):
                checkpoint_cycle_failures = [
                    {"code": str(item.get("code", "")), "detail": str(item.get("detail", ""))}
                    for item in parsed_failures
                    if isinstance(item, dict)
                ]
        except Exception:
            checkpoint_cycle_failures = []

    return JobRead(
        id=job.id,
        title=job.title,
        status=job.status,
        input_bundle_path=job.input_bundle_path,
        assigned_at=job.assigned_at,
        started_at=job.started_at,
        status_changed_at=job.status_changed_at,
        latest_checkpoint_path=job.latest_checkpoint_path,
        last_checkpoint_at=job.last_checkpoint_at,
        progress=job.progress,
        progress_codes=progress_codes,
        checkpoint_cycle_status=job.checkpoint_cycle_status,
        checkpoint_cycle_failures=checkpoint_cycle_failures,
        assigned_worker_id=job.assigned_worker_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


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
        status_changed_at=now,
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
    return _job_to_read(job)


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Cannot prune active-status jobs: {[s.value for s in non_terminal]}",
        )
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than_days)
    result = await session.exec(
        delete(Job).where(
            col(Job.status).in_(job_status),
            col(Job.updated_at) < cutoff,
        )
    )
    await session.commit()
    deleted = result.rowcount or 0
    logger.info("jobs_pruned", count=deleted, older_than_days=older_than_days)
    return {"deleted": deleted}


@router.get("", response_model=list[JobRead])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[JobRead]:
    jobs = (await session.exec(select(Job).order_by(col(Job.created_at).desc()))).all()
    return [_job_to_read(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_to_read(job)


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
    return _job_to_read(requeued_job)
