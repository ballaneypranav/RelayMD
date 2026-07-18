from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
from relaymd_api_client import errors as api_errors
from relaymd_api_client.api.default import heartbeat_worker_workers_worker_id_heartbeat_post
from relaymd_api_client.client import Client as RelaymdApiClient
from relaymd_api_client.models.http_validation_error import (
    HTTPValidationError as ApiHTTPValidationError,
)
from relaymd_api_client.models.worker_heartbeat import WorkerHeartbeat as ApiWorkerHeartbeat
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from relaymd.runtime_defaults import DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS
from relaymd.worker import bootstrap as worker_bootstrap
from relaymd.worker.logging import get_logger

LOG = get_logger(__name__)


def _is_retryable_heartbeat_error(exception: BaseException) -> bool:
    if isinstance(exception, api_errors.UnexpectedStatus):
        return exception.status_code >= 500

    if not isinstance(exception, httpx.HTTPError):
        return False

    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code >= 500

    return isinstance(exception, (httpx.NetworkError, httpx.TimeoutException))


def _heartbeat_error_fields(exception: BaseException) -> dict[str, str]:
    return {
        "error_type": type(exception).__name__,
        "error": str(exception),
    }


@dataclass(frozen=True)
class HeartbeatHealthSnapshot:
    consecutive_failures: int
    degraded_since: float | None
    last_success_at: float | None

    @property
    def is_degraded(self) -> bool:
        return self.degraded_since is not None


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        orchestrator_url: str,
        worker_id: UUID,
        api_token: str,
        interval_seconds: int = 60,
        timeout_seconds: float = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
        stop_event: threading.Event | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"heartbeat-{worker_id}")
        self._orchestrator_url = orchestrator_url.rstrip("/")
        self._worker_id = worker_id
        self._api_token = api_token
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds
        self._stop_event = stop_event or threading.Event()
        self._state_lock = threading.Lock()
        self._job_id: str | None = None
        self._progress: float | None = None
        self._progress_codes: list[str] = []
        now = time.monotonic()
        self._consecutive_failures = 0
        self._degraded_since: float | None = None
        self._last_success_at: float | None = now

    @staticmethod
    def _should_use_tailscale_userspace_proxy() -> bool:
        return Path(worker_bootstrap.tailscale_socket_path()).exists()

    def _build_httpx_args(self) -> dict[str, object]:
        if not self._should_use_tailscale_userspace_proxy():
            return {}

        return {"proxy": worker_bootstrap.tailscale_socks5_proxy_url()}

    def run(self) -> None:
        httpx_args = self._build_httpx_args()
        if httpx_args:
            LOG.info(
                "heartbeat_proxy_enabled",
                proxy_url=worker_bootstrap.tailscale_socks5_proxy_url(),
                tailscale_socket=worker_bootstrap.tailscale_socket_path(),
            )

        with RelaymdApiClient(
            base_url=self._orchestrator_url,
            timeout=httpx.Timeout(self._timeout_seconds),
            httpx_args=httpx_args,
            raise_on_unexpected_status=True,
        ) as client:
            while not self._stop_event.is_set():
                try:
                    self._send(client)
                    self._mark_success()
                except (httpx.HTTPError, api_errors.UnexpectedStatus) as exception:
                    self._mark_failure()
                    error_fields = _heartbeat_error_fields(exception)
                    LOG.warning(
                        "heartbeat_send_failed",
                        worker_id=str(self._worker_id),
                        **error_fields,
                    )
                if self._stop_event.wait(self._interval_seconds):
                    break

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception(_is_retryable_heartbeat_error),
        reraise=True,
    )
    def _send(self, client: RelaymdApiClient) -> None:
        payload = ApiWorkerHeartbeat()
        with self._state_lock:
            if self._job_id is not None:
                payload.job_id = UUID(self._job_id)
            if self._progress is not None:
                payload.progress = self._progress
            payload.progress_codes = list(self._progress_codes)

        response = heartbeat_worker_workers_worker_id_heartbeat_post.sync(
            worker_id=self._worker_id,
            client=client,
            x_api_token=self._api_token,
            body=payload,
        )
        if isinstance(response, ApiHTTPValidationError):
            raise RuntimeError(response.to_dict())

    def set_job_progress(
        self, *, job_id: UUID | None, progress: float | None, progress_codes: list[str] | None
    ) -> None:
        with self._state_lock:
            self._job_id = str(job_id) if job_id is not None else None
            self._progress = progress
            self._progress_codes = list(progress_codes or [])

    def health_snapshot(self) -> HeartbeatHealthSnapshot:
        with self._state_lock:
            return HeartbeatHealthSnapshot(
                consecutive_failures=self._consecutive_failures,
                degraded_since=self._degraded_since,
                last_success_at=self._last_success_at,
            )

    def _mark_success(self) -> None:
        with self._state_lock:
            self._consecutive_failures = 0
            self._degraded_since = None
            self._last_success_at = time.monotonic()

    def _mark_failure(self) -> None:
        with self._state_lock:
            self._consecutive_failures += 1
            if self._degraded_since is None:
                self._degraded_since = time.monotonic()
