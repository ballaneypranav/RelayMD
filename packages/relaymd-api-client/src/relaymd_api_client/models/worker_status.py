from enum import Enum


class WorkerStatus(str, Enum):
    ACTIVE = "active"
    QUEUED = "queued"

    def __str__(self) -> str:
        return str(self.value)
