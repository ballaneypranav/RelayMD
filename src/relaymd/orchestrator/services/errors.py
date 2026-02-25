from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from relaymd.models import JobConflict, JobStatus


class OrchestratorDomainError(RuntimeError):
    """Base type for domain errors raised by orchestrator services."""


@dataclass(slots=True)
class JobTransitionConflictError(OrchestratorDomainError):
    message: str
    current_status: JobStatus | None = None
    requested_status: JobStatus | None = None
    job_id: UUID | None = None

    def to_response_model(self) -> JobConflict:
        return JobConflict(
            message=self.message,
            job_id=self.job_id,
            current_status=self.current_status,
            requested_status=self.requested_status,
        )
