import uuid
from typing import Literal

from sqlmodel import SQLModel


class JobAssigned(SQLModel):
    status: Literal["assigned"] = "assigned"
    job_id: uuid.UUID
    input_bundle_path: str
    latest_checkpoint_path: str | None


class NoJobAvailable(SQLModel):
    status: Literal["no_job_available"] = "no_job_available"


JobRequestResponse = JobAssigned | NoJobAvailable
