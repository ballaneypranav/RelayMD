from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobEvent, JobHistoryEventRead, JobStatus, JobWorkerSegmentRead, JobWorkerTotalRead

JobEventType = Literal[
    "created",
    "assigned",
    "running",
    "checkpoint",
    "requeued_with",
    "requeued_from",
    "completed",
    "failed",
    "cancelled",
    "worker_deregistered_requeue",
]

TERMINAL_EVENT_TYPES = {"completed", "failed", "cancelled"}


async def append_job_event(
    session: AsyncSession,
    *,
    job_id: UUID,
    event_type: JobEventType,
    worker_id: UUID | None,
    status_from: JobStatus | None,
    status_to: JobStatus | None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> JobEvent:
    seq_stmt = select(func.max(JobEvent.event_seq)).where(JobEvent.job_id == job_id)
    with session.no_autoflush:
        max_seq = (await session.exec(seq_stmt)).one_or_none()
    event = JobEvent(
        job_id=job_id,
        event_seq=(int(max_seq) + 1) if max_seq is not None else 1,
        event_type=event_type,
        worker_id=worker_id,
        status_from=status_from,
        status_to=status_to,
        payload_json=json.dumps(payload) if payload is not None else None,
        occurred_at=(occurred_at or datetime.now(UTC).replace(tzinfo=None)),
    )
    session.add(event)
    return event


async def load_job_history_events(session: AsyncSession, *, job_id: UUID) -> list[JobHistoryEventRead]:
    rows = (
        await session.exec(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(col(JobEvent.occurred_at).asc(), col(JobEvent.event_seq).asc())
        )
    ).all()

    events: list[JobHistoryEventRead] = []
    for row in rows:
        payload: dict[str, Any] = {}
        if row.payload_json:
            try:
                parsed = json.loads(row.payload_json)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        events.append(
            JobHistoryEventRead(
                occurred_at=row.occurred_at,
                event_seq=row.event_seq,
                event_type=row.event_type,
                worker_id=row.worker_id,
                status_from=row.status_from,
                status_to=row.status_to,
                payload=payload,
                derived=False,
            )
        )
    return events


def derive_history_events(job: Job) -> list[JobHistoryEventRead]:
    events: list[JobHistoryEventRead] = [
        JobHistoryEventRead(
            occurred_at=job.created_at,
            event_seq=1,
            event_type="created",
            status_to=JobStatus.queued,
            derived=True,
        )
    ]
    seq = 2
    if job.assigned_at is not None:
        events.append(
            JobHistoryEventRead(
                occurred_at=job.assigned_at,
                event_seq=seq,
                event_type="assigned",
                worker_id=job.assigned_worker_id,
                status_to=JobStatus.assigned,
                derived=True,
            )
        )
        seq += 1
    if job.started_at is not None:
        events.append(
            JobHistoryEventRead(
                occurred_at=job.started_at,
                event_seq=seq,
                event_type="running",
                worker_id=job.assigned_worker_id,
                status_to=JobStatus.running,
                derived=True,
            )
        )
        seq += 1
    if job.last_checkpoint_at is not None and job.latest_checkpoint_path:
        events.append(
            JobHistoryEventRead(
                occurred_at=job.last_checkpoint_at,
                event_seq=seq,
                event_type="checkpoint",
                worker_id=job.assigned_worker_id,
                payload={"checkpoint_path": job.latest_checkpoint_path, "progress": job.progress},
                derived=True,
            )
        )
        seq += 1
    if job.status in {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}:
        events.append(
            JobHistoryEventRead(
                occurred_at=job.status_changed_at,
                event_seq=seq,
                event_type=job.status.value,
                worker_id=job.assigned_worker_id,
                status_to=job.status,
                derived=True,
            )
        )
    return sorted(events, key=lambda item: (item.occurred_at, item.event_seq))


def build_worker_runtime(events: list[JobHistoryEventRead], *, now: datetime) -> tuple[list[JobWorkerSegmentRead], list[JobWorkerTotalRead]]:
    segments: list[JobWorkerSegmentRead] = []
    current_worker: UUID | None = None
    segment_start: datetime | None = None

    for event in events:
        if event.event_type in {"assigned", "running"}:
            worker_id = event.worker_id
            if current_worker is not None and segment_start is not None and worker_id != current_worker:
                duration = max(0.0, (event.occurred_at - segment_start).total_seconds())
                segments.append(
                    JobWorkerSegmentRead(
                        worker_id=current_worker,
                        started_at=segment_start,
                        ended_at=event.occurred_at,
                        duration_seconds=duration,
                        open=False,
                    )
                )
                segment_start = None
            if segment_start is None:
                current_worker = worker_id
                segment_start = event.occurred_at
        elif event.event_type in TERMINAL_EVENT_TYPES:
            if current_worker is not None and segment_start is not None:
                duration = max(0.0, (event.occurred_at - segment_start).total_seconds())
                segments.append(
                    JobWorkerSegmentRead(
                        worker_id=current_worker,
                        started_at=segment_start,
                        ended_at=event.occurred_at,
                        duration_seconds=duration,
                        open=False,
                    )
                )
            current_worker = None
            segment_start = None

    if current_worker is not None and segment_start is not None:
        duration = max(0.0, (now - segment_start).total_seconds())
        segments.append(
            JobWorkerSegmentRead(
                worker_id=current_worker,
                started_at=segment_start,
                ended_at=now,
                duration_seconds=duration,
                open=True,
            )
        )

    totals: dict[UUID | None, JobWorkerTotalRead] = {}
    for segment in segments:
        existing = totals.get(segment.worker_id)
        if existing is None:
            totals[segment.worker_id] = JobWorkerTotalRead(
                worker_id=segment.worker_id,
                total_runtime_seconds=segment.duration_seconds,
                segment_count=1,
            )
        else:
            existing.total_runtime_seconds += segment.duration_seconds
            existing.segment_count += 1

    ordered_totals = sorted(totals.values(), key=lambda item: item.total_runtime_seconds, reverse=True)
    return segments, ordered_totals
