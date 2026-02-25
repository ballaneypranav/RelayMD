from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from pydantic_settings.sources import PydanticBaseSettingsSource

from relaymd.runtime_defaults import (
    DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_TIMEOUT_MULTIPLIER,
    DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    DEFAULT_ORPHANED_JOB_REQUEUE_INTERVAL_SECONDS,
    DEFAULT_SALAD_API_TIMEOUT_SECONDS,
    DEFAULT_SBATCH_SUBMISSION_INTERVAL_SECONDS,
    DEFAULT_SBATCH_SUBMIT_TIMEOUT_SECONDS,
    DEFAULT_SIGTERM_CHECKPOINT_POLL_SECONDS,
    DEFAULT_SIGTERM_CHECKPOINT_WAIT_SECONDS,
    DEFAULT_SIGTERM_PROCESS_WAIT_SECONDS,
    DEFAULT_SLURM_SIGTERM_MARGIN_SECONDS,
    DEFAULT_STALE_WORKER_REAPER_INTERVAL_SECONDS,
)
from relaymd.settings_sources import relaymd_config_paths, relaymd_settings_sources

RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"
DEFAULT_RELAYMD_CONFIG_PATH = "~/.config/relaymd/config.yaml"


class ClusterConfig(BaseModel):
    name: str
    partition: str
    account: str
    gpu_type: str
    gpu_count: int
    sif_path: str
    max_pending_jobs: int = 1
    wall_time: str = "4:00:00"


class OrchestratorSettings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./relaymd.db"
    api_token: str = Field(
        default="change-me",
        validation_alias=AliasChoices("api_token", "RELAYMD_API_TOKEN", "API_TOKEN"),
    )
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    heartbeat_timeout_multiplier: float = DEFAULT_HEARTBEAT_TIMEOUT_MULTIPLIER
    stale_worker_reaper_interval_seconds: int = DEFAULT_STALE_WORKER_REAPER_INTERVAL_SECONDS
    orphaned_job_requeue_interval_seconds: int = DEFAULT_ORPHANED_JOB_REQUEUE_INTERVAL_SECONDS
    sbatch_submission_interval_seconds: int = DEFAULT_SBATCH_SUBMISSION_INTERVAL_SECONDS
    sbatch_submit_timeout_seconds: float = DEFAULT_SBATCH_SUBMIT_TIMEOUT_SECONDS
    slurm_sigterm_margin_seconds: int = DEFAULT_SLURM_SIGTERM_MARGIN_SECONDS
    worker_heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    worker_checkpoint_poll_interval_seconds: int = DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS
    worker_orchestrator_timeout_seconds: float = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS
    worker_sigterm_checkpoint_wait_seconds: int = DEFAULT_SIGTERM_CHECKPOINT_WAIT_SECONDS
    worker_sigterm_checkpoint_poll_seconds: int = DEFAULT_SIGTERM_CHECKPOINT_POLL_SECONDS
    worker_sigterm_process_wait_seconds: int = DEFAULT_SIGTERM_PROCESS_WAIT_SECONDS
    infisical_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "infisical_token", "INFISICAL_TOKEN", "RELAYMD_INFISICAL_TOKEN"
        ),
    )
    slurm_cluster_configs: list[ClusterConfig] = []
    salad_api_key: str | None = None
    salad_org: str | None = None
    salad_project: str | None = None
    salad_container_group: str | None = None
    salad_max_replicas: int = 4
    salad_api_timeout_seconds: float = DEFAULT_SALAD_API_TIMEOUT_SECONDS
    relaymd_env: Literal["development", "production"] = "production"
    relaymd_log_level: str = "INFO"
    relaymd_log_format: Literal["auto", "json", "console"] = "auto"

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @classmethod
    def config_paths(cls) -> list[Path]:
        return relaymd_config_paths(
            default_home_config_path=DEFAULT_RELAYMD_CONFIG_PATH,
            config_env_var=RELAYMD_CONFIG_ENV_VAR,
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        _ = (env_settings, dotenv_settings, file_secret_settings)
        return relaymd_settings_sources(
            settings_cls=settings_cls,
            init_settings=init_settings,
            env_override_map={
                "api_token": ("RELAYMD_API_TOKEN", "API_TOKEN"),
                "infisical_token": ("INFISICAL_TOKEN", "RELAYMD_INFISICAL_TOKEN"),
                "salad_api_key": ("SALAD_API_KEY",),
                "salad_org": ("SALAD_ORG",),
                "salad_project": ("SALAD_PROJECT",),
                "salad_container_group": ("SALAD_CONTAINER_GROUP",),
                "salad_max_replicas": ("SALAD_MAX_REPLICAS",),
                "salad_api_timeout_seconds": ("SALAD_API_TIMEOUT_SECONDS",),
                "sbatch_submit_timeout_seconds": ("SBATCH_SUBMIT_TIMEOUT_SECONDS",),
            },
            config_paths=cls.config_paths(),
        )
