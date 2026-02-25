from enum import StrEnum


class JobStatus(StrEnum):
    queued = "queued"
    assigned = "assigned"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Platform(StrEnum):
    hpc = "hpc"
    salad = "salad"
