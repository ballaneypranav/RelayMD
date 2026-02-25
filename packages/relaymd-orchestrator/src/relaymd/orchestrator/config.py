from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from pydantic_settings.sources import DefaultSettingsSource, PydanticBaseSettingsSource

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
        if explicit := os.getenv(RELAYMD_CONFIG_ENV_VAR):
            return [Path(explicit).expanduser()]
        return [
            Path(DEFAULT_RELAYMD_CONFIG_PATH).expanduser(),
            Path.cwd() / "relaymd-config.yaml",
        ]

    @classmethod
    def _drop_yaml_keys_with_env_overrides(
        cls,
        yaml_source: YamlConfigSettingsSource,
    ) -> None:
        env_override_map = {
            "api_token": ("RELAYMD_API_TOKEN", "API_TOKEN"),
            "infisical_token": ("INFISICAL_TOKEN", "RELAYMD_INFISICAL_TOKEN"),
            "salad_api_key": ("SALAD_API_KEY",),
            "salad_org": ("SALAD_ORG",),
            "salad_project": ("SALAD_PROJECT",),
            "salad_container_group": ("SALAD_CONTAINER_GROUP",),
            "salad_max_replicas": ("SALAD_MAX_REPLICAS",),
        }
        init_kwargs = yaml_source.init_kwargs
        if isinstance(init_kwargs, dict):
            config_dicts = [init_kwargs]
        elif isinstance(init_kwargs, list):
            config_dicts = [item for item in init_kwargs if isinstance(item, dict)]
        else:
            config_dicts = []

        for field_name, env_keys in env_override_map.items():
            if any(os.getenv(env_key) is not None for env_key in env_keys):
                for config_dict in config_dicts:
                    config_dict.pop(field_name, None)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=cls.config_paths())
        cls._drop_yaml_keys_with_env_overrides(yaml_source)
        return (
            init_settings,
            yaml_source,
            EnvSettingsSource(settings_cls),
            DefaultSettingsSource(settings_cls),
        )
