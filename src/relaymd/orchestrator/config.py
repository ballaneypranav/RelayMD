from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from pydantic_settings.sources import PydanticBaseSettingsSource

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
    heartbeat_timeout_multiplier: float = 2.0
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
            },
            config_paths=cls.config_paths(),
        )
