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
    latest_checkpoint_path: str | None = None
    last_checkpoint_at: datetime | None = None
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


class JobRead(SQLModel):
    id: uuid.UUID
    title: str
    status: JobStatus
    input_bundle_path: str
    assigned_at: datetime | None
    started_at: datetime | None
    status_changed_at: datetime
    latest_checkpoint_path: str | None
    last_checkpoint_at: datetime | None
    progress: float | None = None
    progress_codes: list[str] = []
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures: list[dict[str, str]] = []
    assigned_worker_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CheckpointReport(SQLModel):
    checkpoint_path: str
    progress: float | None = None
    progress_codes: list[str] = []
    checkpoint_cycle_status: str | None = None
    checkpoint_cycle_failures: list[dict[str, str]] = []


class JobEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: uuid.UUID
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
