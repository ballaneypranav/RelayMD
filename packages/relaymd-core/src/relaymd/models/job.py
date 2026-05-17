import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Field, SQLModel

from .enums import JobStatus


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Job(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    status_changed_at: datetime = Field(default_factory=utcnow_naive)
    title: str
    status: JobStatus = JobStatus.queued
    input_bundle_path: str
    preferred_clusters_json: str | None = None
    comment: str | None = None
    queue_blocked_reason: str | None = None
    latest_checkpoint_manifest_path: str | None = None
    latest_failure_artifact_path: str | None = None
    last_checkpoint_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    progress: float | None = None
    progress_codes_json: str | None = None
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures_json: str | None = None
    assigned_worker_id: uuid.UUID | None = None
    slurm_job_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)


class JobCreate(SQLModel):
    id: uuid.UUID | None = None
    title: str
    input_bundle_path: str
    preferred_clusters: list[str] = []
    comment: str | None = None


class JobRead(SQLModel):
    id: uuid.UUID
    title: str
    status: JobStatus
    input_bundle_path: str
    preferred_clusters: list[str] = []
    comment: str | None = None
    queue_blocked_reason: str | None = None
    assigned_at: datetime | None
    started_at: datetime | None
    status_changed_at: datetime
    latest_checkpoint_manifest_path: str | None
    latest_failure_artifact_path: str | None
    cancellation_requested_at: datetime | None = None
    last_checkpoint_at: datetime | None
    progress: float | None = None
    runtime_seconds: float = 0.0
    etc_seconds: float | None = None
    ett_seconds: float | None = None
    progress_codes: list[str] = []
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures: list[dict[str, str]] = []
    assigned_worker_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CheckpointReport(SQLModel):
    checkpoint_manifest_path: str | None = None
    checkpoint_path: str | None = None
    progress: float | None = None
    progress_codes: list[str] = []
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures: list[dict[str, str]] = []


class HandoffStart(SQLModel):
    reason: str
    progress: float | None = None
    progress_codes: list[str] = []
    deadline_epoch_seconds: float | None = None
    message: str | None = None


class HandoffComplete(SQLModel):
    checkpoint_manifest_path: str | None = None
    checkpoint_path: str | None = None
    progress: float | None = None
    progress_codes: list[str] = []
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures: list[dict[str, str]] = []


class FailJobReport(SQLModel):
    failure_artifact_path: str | None = None
    reason: str | None = None
    detail: str | None = None


class JobEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: uuid.UUID = Field(foreign_key="job.id")
    occurred_at: datetime = Field(default_factory=utcnow_naive)
    event_seq: int
    event_type: str
    worker_id: uuid.UUID | None = None
    status_from: JobStatus | None = None
    status_to: JobStatus | None = None
    payload_json: str | None = None


class JobHistoryEventRead(SQLModel):
    occurred_at: datetime
    event_seq: int
    event_type: str
    worker_id: uuid.UUID | None = None
    status_from: JobStatus | None = None
    status_to: JobStatus | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    derived: bool = False


class JobWorkerSegmentRead(SQLModel):
    worker_id: uuid.UUID | None = None
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    open: bool = False


class JobWorkerTotalRead(SQLModel):
    worker_id: uuid.UUID | None = None
    total_runtime_seconds: float
    segment_count: int


class JobHistoryRead(SQLModel):
    events: list[JobHistoryEventRead]
    worker_segments: list[JobWorkerSegmentRead]
    worker_totals: list[JobWorkerTotalRead]
    derived: bool = False


class WorkerHeartbeat(SQLModel):
    job_id: uuid.UUID | None = None
    progress: float | None = None
    progress_codes: list[str] = []
