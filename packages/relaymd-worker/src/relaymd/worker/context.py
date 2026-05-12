from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from relaymd.runtime_defaults import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS,
    DEFAULT_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER,
)
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
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    heartbeat_failure_grace_multiplier: int = DEFAULT_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER
    heartbeat_failure_grace_floor_seconds: int = (
        DEFAULT_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS
    )
    heartbeat_thread: HeartbeatThread | None = None
