import uuid
from typing import Literal

from sqlmodel import SQLModel

from .enums import JobStatus


class JobAssigned(SQLModel):
    status: Literal["assigned"] = "assigned"
    job_id: uuid.UUID
    input_bundle_path: str
    latest_checkpoint_path: str | None


class NoJobAvailable(SQLModel):
    status: Literal["no_job_available"] = "no_job_available"


class JobConflict(SQLModel):
    error: Literal["job_transition_conflict"] = "job_transition_conflict"
    message: str
    job_id: uuid.UUID | None = None
    current_status: JobStatus | None = None
    requested_status: JobStatus | None = None


class JobCreateConflict(SQLModel):
    message: str
    job_id: uuid.UUID


JobRequestResponse = JobAssigned | NoJobAvailable
