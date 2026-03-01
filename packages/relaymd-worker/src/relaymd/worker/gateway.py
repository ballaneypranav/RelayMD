from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
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
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from relaymd.runtime_defaults import (
    DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    DEFAULT_WORKER_REGISTER_MAX_ATTEMPTS,
)
from relaymd.worker import bootstrap as worker_bootstrap


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
        register_worker_max_attempts: int = DEFAULT_WORKER_REGISTER_MAX_ATTEMPTS,
    ) -> None:
        self._orchestrator_url = orchestrator_url.rstrip("/")
        self._api_token = api_token
        self._logger = logger
        self._timeout_seconds = timeout_seconds
        self._register_worker_max_attempts = max(1, int(register_worker_max_attempts))
        self._client_context: RelaymdApiClient | None = None
        self._client: RelaymdApiClient | None = None

    @staticmethod
    def _should_use_tailscale_userspace_proxy() -> bool:
        return Path(worker_bootstrap.tailscale_socket_path()).exists()

    def _build_httpx_args(self) -> dict[str, object]:
        if not self._should_use_tailscale_userspace_proxy():
            return {}

        return {"proxy": worker_bootstrap.tailscale_socks5_proxy_url()}

    def __enter__(self) -> ApiOrchestratorGateway:
        httpx_args = self._build_httpx_args()
        if httpx_args:
            self._logger.info(
                "orchestrator_gateway_proxy_enabled",
                proxy_url=worker_bootstrap.tailscale_socks5_proxy_url(),
                tailscale_socket=worker_bootstrap.tailscale_socket_path(),
            )

        self._client_context = RelaymdApiClient(
            base_url=self._orchestrator_url,
            timeout=httpx.Timeout(self._timeout_seconds),
            httpx_args=httpx_args,
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

    def _log_register_worker_retry(self, retry_state: RetryCallState) -> None:
        if retry_state.outcome is None:
            return
        exc = retry_state.outcome.exception()
        next_action = retry_state.next_action
        wait_seconds = 0.0 if next_action is None else next_action.sleep
        self._logger.warning(
            "register_worker_retrying",
            attempt=retry_state.attempt_number,
            max_attempts=self._register_worker_max_attempts,
            wait_seconds=wait_seconds,
            error_type=type(exc).__name__ if exc is not None else None,
            error=str(exc) if exc is not None else None,
        )

    @staticmethod
    def _is_retryable_register_error(exception: BaseException) -> bool:
        if isinstance(exception, api_errors.UnexpectedStatus):
            return exception.status_code >= 500

        if not isinstance(exception, httpx.HTTPError):
            return False

        if isinstance(exception, httpx.HTTPStatusError):
            return exception.response.status_code >= 500

        return isinstance(exception, (httpx.NetworkError, httpx.TimeoutException))

    def _register_worker_once(
        self,
        *,
        platform: ApiPlatform,
        gpu_model: str,
        gpu_count: int,
        vram_gb: int,
        provider_id: str | None = None,
    ) -> UUID:
        response = register_worker_workers_register_post.sync(
            client=self.client,
            body=ApiWorkerRegister(
                platform=platform,
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
                provider_id=provider_id,
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

    def register_worker(
        self,
        *,
        platform: ApiPlatform,
        gpu_model: str,
        gpu_count: int,
        vram_gb: int,
        provider_id: str | None = None,
    ) -> UUID:
        retrying = Retrying(
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(self._register_worker_max_attempts),
            retry=retry_if_exception(self._is_retryable_register_error),
            before_sleep=self._log_register_worker_retry,
            reraise=True,
        )

        try:
            return retrying(
                self._register_worker_once,
                platform=platform,
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
                provider_id=provider_id,
            )
        except Exception as exc:  # noqa: BLE001
            if not self._is_retryable_register_error(exc):
                raise

            raise RuntimeError(
                "Failed to register worker with orchestrator "
                f"{self._orchestrator_url} after {self._register_worker_max_attempts} attempts. "
                "Verify orchestrator reachability and worker timeout/retry settings."
            ) from exc

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
