from enum import StrEnum


class JobStatus(StrEnum):
    queued = "queued"
    assigned = "assigned"
    running = "running"
    handoff = "handoff"
    cancelling = "cancelling"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Platform(StrEnum):
    hpc = "hpc"
    salad = "salad"


class WorkerStatus(StrEnum):
    queued = "queued"  # submitted to provider, not yet started
    active = "active"  # worker process registered and heartbeating
