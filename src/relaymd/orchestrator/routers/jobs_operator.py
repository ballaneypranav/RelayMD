from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import (
    Job,
    JobConflict,
    JobCreate,
    JobCreateConflict,
    JobHistoryRead,
    JobRead,
    JobStatus,
)
from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services import JobTransitionConflictError, JobTransitionService
from relaymd.orchestrator.services.cluster_provisioning_state_service import (
    ClusterProvisioningStateService,
)
from relaymd.orchestrator.services.job_history_service import (
    append_job_event,
    build_worker_runtime,
    derive_history_events,
    load_job_history_events,
    load_job_history_events_for_jobs,
)

from ._responses import job_transition_conflict_response

router = APIRouter(prefix="/jobs", dependencies=[Depends(require_worker_api_token)])
logger = structlog.get_logger(__name__)


def _normalize_preferred_clusters(
    cluster_names: list[str],
    *,
    known_cluster_names: set[str],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in cluster_names:
        name = value.strip()
        if not name:
            continue
        if name not in known_cluster_names:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": "unknown_preferred_cluster",
                    "cluster_name": name,
                    "known_cluster_names": sorted(known_cluster_names),
                },
            )
        if name not in seen:
            seen.add(name)
            normalized.append(name)
    return normalized


def _normalize_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    trimmed = comment.strip()
    if not trimmed:
        return None
    if len(trimmed) > 2000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="comment must be 2000 characters or fewer",
        )
    return trimmed


def _compute_queue_blocked_reason(
    *,
    preferred_clusters: list[str],
    known_cluster_names: set[str],
    enabled_map: dict[str, bool],
) -> str | None:
    if not preferred_clusters:
        return None
    if not any(cluster in known_cluster_names for cluster in preferred_clusters):
        return "no_matching_pinned_clusters"
    if not any(enabled_map.get(cluster, False) for cluster in preferred_clusters):
        return "no_enabled_pinned_clusters"
    return None


def _job_to_read(job: Job) -> JobRead:
    progress_codes: list[str] = []
    checkpoint_cycle_failures: list[dict[str, str]] = []
    preferred_clusters: list[str] = []
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
    if job.preferred_clusters_json:
        try:
            parsed_clusters = json.loads(job.preferred_clusters_json)
            if isinstance(parsed_clusters, list):
                preferred_clusters = [
                    name for item in parsed_clusters if (name := str(item).strip())
                ]
        except Exception:
            preferred_clusters = []

    return JobRead(
        id=job.id,
        title=job.title,
        status=job.status,
        input_bundle_path=job.input_bundle_path,
        preferred_clusters=preferred_clusters,
        comment=job.comment,
        queue_blocked_reason=job.queue_blocked_reason,
        assigned_at=job.assigned_at,
        started_at=job.started_at,
        status_changed_at=job.status_changed_at,
        latest_checkpoint_manifest_path=job.latest_checkpoint_manifest_path,
        latest_checkpoint_path=job.latest_checkpoint_manifest_path,
        last_checkpoint_at=job.last_checkpoint_at,
        cancellation_requested_at=job.cancellation_requested_at,
        progress=job.progress,
        runtime_seconds=0.0,
        etc_seconds=None,
        ett_seconds=None,
        progress_codes=progress_codes,
        checkpoint_cycle_status=job.checkpoint_cycle_status,
        checkpoint_cycle_failures=checkpoint_cycle_failures,
        assigned_worker_id=job.assigned_worker_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _compute_eta_fields(
    *,
    status: JobStatus,
    progress: float | None,
    runtime_seconds: float,
) -> tuple[float | None, float | None]:
    if status not in {JobStatus.assigned, JobStatus.running}:
        return None, None
    clamped_progress = max(0.0, min(1.0, float(progress or 0.0)))
    if clamped_progress <= 0.0 or clamped_progress >= 1.0:
        return None, None
    etc_seconds = max((runtime_seconds / clamped_progress) - runtime_seconds, 0.0)
    return etc_seconds, runtime_seconds + etc_seconds


async def _job_to_read_with_runtime(session: AsyncSession, job: Job) -> JobRead:
    job_read = _job_to_read(job)
    events = await load_job_history_events(session, job_id=job.id)
    if not events:
        events = derive_history_events(job)
    now = datetime.now(UTC).replace(tzinfo=None)
    segments, _ = build_worker_runtime(events, now=now)
    runtime_seconds = sum(max(segment.duration_seconds, 0.0) for segment in segments)
    etc_seconds, ett_seconds = _compute_eta_fields(
        status=job.status,
        progress=job.progress,
        runtime_seconds=runtime_seconds,
    )
    job_read.runtime_seconds = runtime_seconds
    job_read.etc_seconds = etc_seconds
    job_read.ett_seconds = ett_seconds
    return job_read


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
    request: Request,
    payload: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead | JSONResponse:
    settings: OrchestratorSettings = request.app.state.settings
    known_cluster_names = {cluster.name for cluster in settings.slurm_cluster_configs}
    normalized_clusters = _normalize_preferred_clusters(
        payload.preferred_clusters, known_cluster_names=known_cluster_names
    )
    normalized_comment = _normalize_comment(payload.comment)
    enabled_map = await ClusterProvisioningStateService(session).get_enabled_map(
        settings.slurm_cluster_configs
    )
    queue_blocked_reason = _compute_queue_blocked_reason(
        preferred_clusters=normalized_clusters,
        known_cluster_names=known_cluster_names,
        enabled_map=enabled_map,
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    job = Job(
        id=payload.id if payload.id is not None else uuid4(),
        title=payload.title,
        input_bundle_path=payload.input_bundle_path,
        preferred_clusters_json=(json.dumps(normalized_clusters) if normalized_clusters else None),
        comment=normalized_comment,
        queue_blocked_reason=queue_blocked_reason,
        status=JobStatus.queued,
        created_at=now,
        status_changed_at=now,
        updated_at=now,
    )
    session.add(job)
    await append_job_event(
        session,
        job_id=job.id,
        event_type="created",
        worker_id=None,
        status_from=None,
        status_to=JobStatus.queued,
    )
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
    return await _job_to_read_with_runtime(session, job)


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
    history_events_by_job_id = await load_job_history_events_for_jobs(
        session, job_ids=[job.id for job in jobs]
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    job_reads: list[JobRead] = []
    for job in jobs:
        job_read = _job_to_read(job)
        events = history_events_by_job_id.get(job.id) or derive_history_events(job)
        segments, _ = build_worker_runtime(events, now=now)
        runtime_seconds = sum(max(segment.duration_seconds, 0.0) for segment in segments)
        etc_seconds, ett_seconds = _compute_eta_fields(
            status=job.status,
            progress=job.progress,
            runtime_seconds=runtime_seconds,
        )
        job_read.runtime_seconds = runtime_seconds
        job_read.etc_seconds = etc_seconds
        job_read.ett_seconds = ett_seconds
        job_reads.append(job_read)
    return job_reads


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return await _job_to_read_with_runtime(session, job)


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
                requested_status=JobStatus.cancelling,
            )
        )

    transitions = JobTransitionService()
    try:
        previous_status = job.status
        cancelled_worker_id = job.assigned_worker_id
        if job.status == JobStatus.queued:
            transitions.cancel_job(job)
            event_type = "cancelled"
            status_to = JobStatus.cancelled
        else:
            transitions.request_job_cancellation(job)
            event_type = "cancel_requested"
            status_to = JobStatus.cancelling
    except JobTransitionConflictError as exc:
        return job_transition_conflict_response(exc)

    session.add(job)
    await append_job_event(
        session,
        job_id=job.id,
        event_type=event_type,
        worker_id=cancelled_worker_id,
        status_from=previous_status,
        status_to=status_to,
    )
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
    request: Request,
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

    settings: OrchestratorSettings = request.app.state.settings
    known_cluster_names = {cluster.name for cluster in settings.slurm_cluster_configs}
    preferred_clusters: list[str] = []
    if requeued_job.preferred_clusters_json:
        try:
            parsed = json.loads(requeued_job.preferred_clusters_json)
            if isinstance(parsed, list):
                preferred_clusters = [name for item in parsed if (name := str(item).strip())]
        except Exception:
            preferred_clusters = []
    enabled_map = await ClusterProvisioningStateService(session).get_enabled_map(
        settings.slurm_cluster_configs
    )
    requeued_job.queue_blocked_reason = _compute_queue_blocked_reason(
        preferred_clusters=preferred_clusters,
        known_cluster_names=known_cluster_names,
        enabled_map=enabled_map,
    )

    session.add(existing_job)
    session.add(requeued_job)
    await append_job_event(
        session,
        job_id=existing_job.id,
        event_type="requeued_with",
        worker_id=existing_job.assigned_worker_id,
        status_from=existing_job.status,
        status_to=existing_job.status,
        payload={"new_job_id": str(requeued_job.id)},
    )
    await append_job_event(
        session,
        job_id=requeued_job.id,
        event_type="requeued_from",
        worker_id=None,
        status_from=None,
        status_to=JobStatus.queued,
        payload={"old_job_id": str(existing_job.id)},
    )
    await session.commit()
    await session.refresh(requeued_job)
    return await _job_to_read_with_runtime(session, requeued_job)


@router.get("/{job_id}/history", response_model=JobHistoryRead)
async def get_job_history(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobHistoryRead:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    events = await load_job_history_events(session, job_id=job_id)
    derived = False
    if not events:
        events = derive_history_events(job)
        derived = True

    now = datetime.now(UTC).replace(tzinfo=None)
    segments, totals = build_worker_runtime(events, now=now)
    return JobHistoryRead(
        events=events,
        worker_segments=segments,
        worker_totals=totals,
        derived=derived,
    )
