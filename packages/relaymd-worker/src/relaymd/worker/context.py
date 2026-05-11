from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from relaymd.storage import StorageClient
from relaymd.worker.gateway import OrchestratorGateway
from relaymd.worker.heartbeat import HeartbeatThread


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
    openmm_platforms: list[str] = field(default_factory=list)
    heartbeat_thread: HeartbeatThread | None = None
