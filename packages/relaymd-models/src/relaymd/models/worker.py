import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from .enums import Platform


class Worker(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    last_heartbeat: datetime = Field(default_factory=datetime.utcnow)
    registered_at: datetime = Field(default_factory=datetime.utcnow)


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
    last_heartbeat: datetime
