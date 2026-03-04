from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from relaymd.runtime_defaults import (
    DEFAULT_CF_WORKER_URL,
    DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    DEFAULT_SIGTERM_CHECKPOINT_POLL_SECONDS,
    DEFAULT_SIGTERM_CHECKPOINT_WAIT_SECONDS,
    DEFAULT_SIGTERM_PROCESS_WAIT_SECONDS,
    DEFAULT_WORKER_REGISTER_MAX_ATTEMPTS,
)


class WorkerRuntimeSettings(BaseSettings):
    worker_platform: str = Field(
        default="salad",
        validation_alias=AliasChoices("worker_platform", "WORKER_PLATFORM", "RELAYMD_PLATFORM"),
    )
    heartbeat_interval_seconds: int = Field(
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        validation_alias=AliasChoices(
            "heartbeat_interval_seconds",
            "HEARTBEAT_INTERVAL_SECONDS",
            "RELAYMD_WORKER_HEARTBEAT_INTERVAL_SECONDS",
        ),
    )
    checkpoint_poll_interval_seconds: int = Field(
        default=DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS,
        validation_alias=AliasChoices(
            "checkpoint_poll_interval_seconds",
            "CHECKPOINT_POLL_INTERVAL_SECONDS",
            "RELAYMD_WORKER_CHECKPOINT_POLL_INTERVAL_SECONDS",
        ),
    )
    orchestrator_timeout_seconds: float = Field(
        default=DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
        validation_alias=AliasChoices(
            "orchestrator_timeout_seconds",
            "ORCHESTRATOR_TIMEOUT_SECONDS",
            "RELAYMD_WORKER_ORCHESTRATOR_TIMEOUT_SECONDS",
        ),
    )
    orchestrator_register_max_attempts: int = Field(
        default=DEFAULT_WORKER_REGISTER_MAX_ATTEMPTS,
        validation_alias=AliasChoices(
            "orchestrator_register_max_attempts",
            "ORCHESTRATOR_REGISTER_MAX_ATTEMPTS",
            "RELAYMD_WORKER_ORCHESTRATOR_REGISTER_MAX_ATTEMPTS",
        ),
    )
    cf_worker_url: str = Field(
        default=DEFAULT_CF_WORKER_URL,
        validation_alias=AliasChoices("cf_worker_url", "CF_WORKER_URL"),
    )
    cf_bearer_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "cf_bearer_token",
            "CF_BEARER_TOKEN",
            "DOWNLOAD_BEARER_TOKEN",
        ),
    )
    sigterm_checkpoint_wait_seconds: int = Field(
        default=DEFAULT_SIGTERM_CHECKPOINT_WAIT_SECONDS,
        validation_alias=AliasChoices(
            "sigterm_checkpoint_wait_seconds",
            "SIGTERM_CHECKPOINT_WAIT_SECONDS",
            "RELAYMD_WORKER_SIGTERM_CHECKPOINT_WAIT_SECONDS",
        ),
    )
    sigterm_checkpoint_poll_seconds: int = Field(
        default=DEFAULT_SIGTERM_CHECKPOINT_POLL_SECONDS,
        validation_alias=AliasChoices(
            "sigterm_checkpoint_poll_seconds",
            "SIGTERM_CHECKPOINT_POLL_SECONDS",
            "RELAYMD_WORKER_SIGTERM_CHECKPOINT_POLL_SECONDS",
        ),
    )
    sigterm_process_wait_seconds: int = Field(
        default=DEFAULT_SIGTERM_PROCESS_WAIT_SECONDS,
        validation_alias=AliasChoices(
            "sigterm_process_wait_seconds",
            "SIGTERM_PROCESS_WAIT_SECONDS",
            "RELAYMD_WORKER_SIGTERM_PROCESS_WAIT_SECONDS",
        ),
    )
    idle_strategy: Literal["immediate_exit", "poll_then_exit"] = Field(
        default="immediate_exit",
        validation_alias=AliasChoices(
            "idle_strategy",
            "IDLE_STRATEGY",
            "RELAYMD_WORKER_IDLE_STRATEGY",
        ),
    )
    idle_poll_interval_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "idle_poll_interval_seconds",
            "IDLE_POLL_INTERVAL_SECONDS",
            "RELAYMD_WORKER_IDLE_POLL_INTERVAL_SECONDS",
        ),
    )
    idle_poll_max_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "idle_poll_max_seconds",
            "IDLE_POLL_MAX_SECONDS",
            "RELAYMD_WORKER_IDLE_POLL_MAX_SECONDS",
        ),
    )
    axiom_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "axiom_token",
            "AXIOM_TOKEN",
            "RELAYMD_AXIOM_TOKEN",
        ),
    )
    axiom_dataset: str = Field(
        default="relaymd",
        validation_alias=AliasChoices(
            "axiom_dataset",
            "AXIOM_DATASET",
            "RELAYMD_AXIOM_DATASET",
        ),
    )

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
