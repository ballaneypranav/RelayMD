import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from .enums import Platform


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Worker(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    slurm_job_id: str | None = None
    last_heartbeat: datetime = Field(default_factory=utcnow_naive)
    registered_at: datetime = Field(default_factory=utcnow_naive)


class WorkerRegister(SQLModel):
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int


class WorkerRead(SQLModel):
    id: uuid.UUID
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    slurm_job_id: str | None = None
    last_heartbeat: datetime
