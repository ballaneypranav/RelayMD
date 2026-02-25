from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from relaymd.storage import StorageClient
from relaymd.worker.gateway import OrchestratorGateway


@dataclass
class WorkerContext:
    gateway: OrchestratorGateway
    storage: StorageClient
    shutdown_event: threading.Event
    checkpoint_poll_interval_seconds: int
    sigterm_checkpoint_wait_seconds: int
    sigterm_checkpoint_poll_seconds: int
    sigterm_process_wait_seconds: int
    logger: Any
