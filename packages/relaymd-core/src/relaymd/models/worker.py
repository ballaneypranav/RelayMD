import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from .enums import Platform, WorkerStatus


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Worker(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    status: WorkerStatus = WorkerStatus.active
    # Opaque reference to the provider-side allocation that spawned this worker.
    # Format is provider-specific:
    #   HPC/SLURM : "<cluster_name>:<slurm_job_id>"  e.g. "gilbreth:12345"
    #   Salad     : "<salad-machine-id>"              (TBD)
    # NULL on workers registered without an associated provisioning event.
    provider_id: str | None = None
    last_heartbeat: datetime = Field(default_factory=utcnow_naive)
    registered_at: datetime = Field(default_factory=utcnow_naive)


class WorkerRegister(SQLModel):
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    # Workers pass their full provider_id on registration so the orchestrator can
    # activate (and de-queue) the matching placeholder row in place.
    # For SLURM workers: f"{RELAYMD_CLUSTER_NAME}:{SLURM_JOB_ID}" injected by sbatch.
    provider_id: str | None = None


class WorkerRead(SQLModel):
    id: uuid.UUID
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    status: WorkerStatus
    provider_id: str | None = None
    last_heartbeat: datetime
