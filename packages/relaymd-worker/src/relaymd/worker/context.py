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
    logger: Any
