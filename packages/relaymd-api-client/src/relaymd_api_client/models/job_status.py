from enum import Enum


class JobStatus(str, Enum):
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    HANDOFF = "handoff"
    QUEUED = "queued"
    RUNNING = "running"

    def __str__(self) -> str:
        return str(self.value)
