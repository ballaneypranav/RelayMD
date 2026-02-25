from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast
from uuid import UUID

import httpx
from relaymd_api_client import errors as api_errors
from relaymd_api_client.api.default import (
    complete_job_jobs_job_id_complete_post,
    deregister_worker_workers_worker_id_deregister_post,
    fail_job_jobs_job_id_fail_post,
    register_worker_workers_register_post,
    report_checkpoint_jobs_job_id_checkpoint_post,
    request_job_jobs_request_post,
)
from relaymd_api_client.client import Client as RelaymdApiClient
from relaymd_api_client.models.checkpoint_report import CheckpointReport as ApiCheckpointReport
from relaymd_api_client.models.http_validation_error import (
    HTTPValidationError as ApiHTTPValidationError,
)
from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable
from relaymd_api_client.models.platform import Platform as ApiPlatform
from relaymd_api_client.models.worker_register import WorkerRegister as ApiWorkerRegister

from relaymd.runtime_defaults import DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS


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

    def report_checkpoint(self, *, job_id: UUID, checkpoint_path: str) -> None: ...

    def complete_job(self, *, job_id: UUID) -> None: ...

    def fail_job(self, *, job_id: UUID) -> None: ...

    def deregister_worker(self, *, worker_id: UUID) -> None: ...


class ApiOrchestratorGateway:
    def __init__(
        self,
        *,
        orchestrator_url: str,
        api_token: str,
        logger: Any,
        timeout_seconds: float = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    ) -> None:
        self._orchestrator_url = orchestrator_url.rstrip("/")
        self._api_token = api_token
        self._logger = logger
        self._timeout_seconds = timeout_seconds
        self._client_context: RelaymdApiClient | None = None
        self._client: RelaymdApiClient | None = None

    def __enter__(self) -> ApiOrchestratorGateway:
        self._client_context = RelaymdApiClient(
            base_url=self._orchestrator_url,
            timeout=httpx.Timeout(self._timeout_seconds),
            raise_on_unexpected_status=True,
        )
        self._client = self._client_context.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._client_context is None:
            return False
        return bool(self._client_context.__exit__(exc_type, exc, tb))

    @property
    def client(self) -> RelaymdApiClient:
        if self._client is None:
            raise RuntimeError("Gateway client is not initialized")
        return self._client

    @staticmethod
    def _raise_if_validation_error(response: object) -> None:
        if isinstance(response, ApiHTTPValidationError):
            raise RuntimeError(response.to_dict())

    @staticmethod
    def _is_conflict_response(response: object) -> bool:
        if response is None:
            return False
        if getattr(response, "error", None) == "job_transition_conflict":
            return True
        if isinstance(response, dict) and response.get("error") == "job_transition_conflict":
            return True
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            payload = cast(dict[str, object], to_dict())
            return payload.get("error") == "job_transition_conflict"
        return False

    def _is_conflict_exception(self, exc: Exception) -> bool:
        if not isinstance(exc, api_errors.UnexpectedStatus):
            return False
        return exc.status_code == 409

    def _call_with_conflict_handling(
        self,
        *,
        job_id: UUID,
        log_event: str,
        api_call: Callable[[], object],
    ) -> None:
        try:
            response = api_call()
        except Exception as exc:  # noqa: BLE001
            if self._is_conflict_exception(exc):
                self._logger.warning(log_event, job_id=str(job_id))
                return
            raise

        self._raise_if_validation_error(response)
        if self._is_conflict_response(response):
            self._logger.warning(log_event, job_id=str(job_id))

    def register_worker(
        self,
        *,
        platform: ApiPlatform,
        gpu_model: str,
        gpu_count: int,
        vram_gb: int,
    ) -> UUID:
        response = register_worker_workers_register_post.sync(
            client=self.client,
            body=ApiWorkerRegister(
                platform=platform,
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
            ),
            x_api_token=self._api_token,
        )
        self._raise_if_validation_error(response)
        if response is None:
            raise RuntimeError("Failed to register worker")
        try:
            return UUID(str(cast(Any, response)["worker_id"]))
        except Exception as exc:  # pragma: no cover - defensive guard for malformed payloads
            raise RuntimeError("Failed to parse worker registration response") from exc

    def request_job(self, *, worker_id: UUID) -> ApiJobAssigned | ApiNoJobAvailable:
        response = request_job_jobs_request_post.sync(
            client=self.client,
            worker_id=worker_id,
            x_api_token=self._api_token,
        )
        self._raise_if_validation_error(response)
        if not isinstance(response, (ApiJobAssigned, ApiNoJobAvailable)):
            raise RuntimeError("Failed to parse job assignment response")
        return response

    def report_checkpoint(self, *, job_id: UUID, checkpoint_path: str) -> None:
        self._call_with_conflict_handling(
            job_id=job_id,
            log_event="checkpoint_conflict_ignored",
            api_call=lambda: report_checkpoint_jobs_job_id_checkpoint_post.sync(
                job_id=job_id,
                client=self.client,
                body=ApiCheckpointReport(checkpoint_path=checkpoint_path),
                x_api_token=self._api_token,
            ),
        )

    def complete_job(self, *, job_id: UUID) -> None:
        self._call_with_conflict_handling(
            job_id=job_id,
            log_event="complete_conflict_ignored",
            api_call=lambda: complete_job_jobs_job_id_complete_post.sync(
                job_id=job_id,
                client=self.client,
                x_api_token=self._api_token,
            ),
        )

    def fail_job(self, *, job_id: UUID) -> None:
        self._call_with_conflict_handling(
            job_id=job_id,
            log_event="fail_conflict_ignored",
            api_call=lambda: fail_job_jobs_job_id_fail_post.sync(
                job_id=job_id,
                client=self.client,
                x_api_token=self._api_token,
            ),
        )

    def deregister_worker(self, *, worker_id: UUID) -> None:
        try:
            response = deregister_worker_workers_worker_id_deregister_post.sync(
                worker_id=worker_id,
                client=self.client,
                x_api_token=self._api_token,
            )
        except api_errors.UnexpectedStatus as exc:
            if exc.status_code == 404:
                self._logger.warning("worker_already_deregistered", worker_id=str(worker_id))
                return
            raise

        self._raise_if_validation_error(response)
