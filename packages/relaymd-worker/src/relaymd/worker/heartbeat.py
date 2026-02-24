from __future__ import annotations

import threading
from uuid import UUID

import httpx
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
        headers = {"X-API-Token": self._api_token}
        with httpx.Client(
            base_url=self._orchestrator_url,
            headers=headers,
            timeout=ORCHESTRATOR_TIMEOUT_SECONDS,
        ) as client:
            while not self._stop_event.is_set():
                try:
                    response = client.post(f"/workers/{self._worker_id}/heartbeat")
                    response.raise_for_status()
                except httpx.HTTPError:
                    LOG.warning(
                        "heartbeat_send_failed",
                        worker_id=str(self._worker_id),
                        exc_info=True,
                    )
                if self._stop_event.wait(self._interval_seconds):
                    break
