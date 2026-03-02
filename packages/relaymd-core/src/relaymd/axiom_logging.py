from __future__ import annotations

import atexit
import queue
import threading
import time
import urllib.error
import urllib.request
from contextlib import suppress

import orjson
import structlog


class AxiomSenderThread(threading.Thread):
    def __init__(
        self, axiom_token: str, dataset: str, flush_interval: float = 2.0, max_batch_size: int = 100
    ) -> None:
        super().__init__(name="AxiomSenderThread", daemon=True)
        self.axiom_token = axiom_token
        self.dataset = dataset
        self.flush_interval = flush_interval
        self.max_batch_size = max_batch_size
        self._queue: queue.Queue[structlog.types.EventDict] = queue.Queue(maxsize=10000)
        self._stop_event = threading.Event()
        self.url = f"https://api.axiom.co/v1/datasets/{self.dataset}/ingest"

    def enqueue(self, event_dict: structlog.types.EventDict) -> None:
        with suppress(queue.Full):
            self._queue.put_nowait(event_dict)

    def run(self) -> None:
        while not self._stop_event.is_set():
            batch = self._gather_batch()
            if batch:
                self._send_batch(batch)
            elif not self._stop_event.is_set():
                # Avoid spinning if the queue is empty
                time.sleep(0.1)

    def _gather_batch(self) -> list[structlog.types.EventDict]:
        batch = []
        with suppress(queue.Empty):
            # Wait up to flush_interval for the first item
            item = self._queue.get(timeout=self.flush_interval)
            batch.append(item)
            # Fetch remaining eagerly up to max_batch_size
            while len(batch) < self.max_batch_size:
                item = self._queue.get_nowait()
                batch.append(item)
        return batch

    def _send_batch(self, batch: list[structlog.types.EventDict]) -> None:
        try:
            payload = orjson.dumps(batch)
            req = urllib.request.Request(
                self.url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.axiom_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "relaymd-axiom-logger/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0):
                pass
        except Exception as exc:
            import datetime
            import sys

            now = datetime.datetime.now(datetime.UTC).isoformat()
            sys.stderr.write(
                f"[{now}] relaymd-axiom-logger: failed to send batch of {len(batch)} logs: {exc}\n"
            )

    def stop(self) -> None:
        self._stop_event.set()
        # Send one last batch if any are lingering
        batch = self._gather_batch()
        if batch:
            self._send_batch(batch)


_AXIOM_THREAD: AxiomSenderThread | None = None


def get_axiom_thread(axiom_token: str, dataset: str) -> AxiomSenderThread:
    global _AXIOM_THREAD
    if _AXIOM_THREAD is None:
        _AXIOM_THREAD = AxiomSenderThread(axiom_token=axiom_token, dataset=dataset)
        _AXIOM_THREAD.start()
        atexit.register(_cleanup_axiom_thread)
    return _AXIOM_THREAD


def _cleanup_axiom_thread() -> None:
    global _AXIOM_THREAD
    if _AXIOM_THREAD is not None:
        _AXIOM_THREAD.stop()
        _AXIOM_THREAD.join(timeout=2.0)
        _AXIOM_THREAD = None


class AxiomProcessor:
    """A structlog processor that queues log dictionaries for Axiom ingestion."""

    def __init__(self, axiom_token: str, dataset: str) -> None:
        self.thread = get_axiom_thread(axiom_token, dataset)

    def __call__(
        self,
        logger: structlog.types.WrappedLogger,
        method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        # Copy the event_dict so modifications down the pipeline don't mutate our view
        dict_copy = dict(event_dict)
        # Ensure timestamp field matches what axiom parses natively
        if "timestamp" in dict_copy and "_time" not in dict_copy:
            dict_copy["_time"] = dict_copy["timestamp"]

        self.thread.enqueue(dict_copy)
        return event_dict
