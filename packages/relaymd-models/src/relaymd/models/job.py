import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from .enums import JobStatus


class Job(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    status: JobStatus = JobStatus.queued
    input_bundle_path: str
    latest_checkpoint_path: str | None = None
    last_checkpoint_at: datetime | None = None
    assigned_worker_id: uuid.UUID | None = None
    slurm_job_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class JobCreate(SQLModel):
    title: str
    input_bundle_path: str


class JobRead(SQLModel):
    id: uuid.UUID
    title: str
    status: JobStatus
    input_bundle_path: str
    latest_checkpoint_path: str | None
    last_checkpoint_at: datetime | None
    assigned_worker_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CheckpointReport(SQLModel):
    checkpoint_path: str
