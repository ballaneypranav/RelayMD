from __future__ import annotations

import threading
from uuid import UUID

import httpx
from relaymd_api_client import errors as api_errors
from relaymd_api_client.api.default import heartbeat_worker_workers_worker_id_heartbeat_post
from relaymd_api_client.client import Client as RelaymdApiClient
from relaymd_api_client.models.http_validation_error import HTTPValidationError as ApiHTTPValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from relaymd.worker.logging import get_logger

LOG = get_logger(__name__)
ORCHESTRATOR_TIMEOUT_SECONDS = 30.0


class HeartbeatThread(threading.Thread):
    def __init__(
        self,
        orchestrator_url: str,
        worker_id: UUID,
        api_token: str,
        interval_seconds: int = 60,
        stop_event: threading.Event | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"heartbeat-{worker_id}")
        self._orchestrator_url = orchestrator_url.rstrip("/")
        self._worker_id = worker_id
        self._api_token = api_token
        self._interval_seconds = interval_seconds
        self._stop_event = stop_event or threading.Event()

    def run(self) -> None:
        with RelaymdApiClient(
            base_url=self._orchestrator_url,
            timeout=httpx.Timeout(ORCHESTRATOR_TIMEOUT_SECONDS),
            raise_on_unexpected_status=True,
        ) as client:
            while not self._stop_event.is_set():
                try:
                    self._send(client)
                except (httpx.HTTPError, api_errors.UnexpectedStatus):
                    LOG.warning(
                        "heartbeat_send_failed",
                        worker_id=str(self._worker_id),
                        exc_info=True,
                    )
                if self._stop_event.wait(self._interval_seconds):
                    break

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.HTTPError, api_errors.UnexpectedStatus)),
        reraise=True,
    )
    def _send(self, client: RelaymdApiClient) -> None:
        response = heartbeat_worker_workers_worker_id_heartbeat_post.sync(
            worker_id=self._worker_id,
            client=client,
            x_api_token=self._api_token,
        )
        if isinstance(response, ApiHTTPValidationError):
            raise RuntimeError(response.to_dict())
