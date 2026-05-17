from __future__ import annotations

from typing import Protocol
from uuid import UUID

from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable
from relaymd_api_client.models.platform import Platform as ApiPlatform


class OrchestratorGateway(Protocol):
    def register_worker(
        self,
        *,
        platform: ApiPlatform,
        gpu_model: str,
        gpu_count: int,
        vram_gb: int,
    ) -> UUID: ...

    def request_job(self, *, worker_id: UUID) -> ApiJobAssigned | ApiNoJobAvailable: ...

    def report_checkpoint(  # noqa: PLR0913
        self,
        *,
        job_id: UUID,
        checkpoint_manifest_path: str | None = None,
        checkpoint_path: str | None = None,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
        checkpoint_cycle_status: str | None = None,
        checkpoint_cycle_failures: list[dict[str, str]] | None = None,
    ) -> None: ...

    def start_job(self, *, job_id: UUID) -> None: ...

    def start_handoff(  # noqa: PLR0913
        self,
        *,
        job_id: UUID,
        reason: str,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
        deadline_epoch_seconds: float | None = None,
        message: str | None = None,
    ) -> None: ...

    def is_cancellation_requested(self, *, job_id: UUID) -> bool: ...

    def complete_job(self, *, job_id: UUID) -> None: ...

    def complete_handoff(  # noqa: PLR0913
        self,
        *,
        job_id: UUID,
        checkpoint_manifest_path: str | None = None,
        checkpoint_path: str | None = None,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
        checkpoint_cycle_status: str | None = None,
        checkpoint_cycle_failures: list[dict[str, str]] | None = None,
    ) -> None: ...

    def fail_job(
        self,
        *,
        job_id: UUID,
        failure_artifact_path: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
    ) -> None: ...

    def deregister_worker(self, *, worker_id: UUID) -> None: ...
