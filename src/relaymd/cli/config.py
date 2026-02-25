from __future__ import annotations

import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from pydantic_settings.sources import DefaultSettingsSource, PydanticBaseSettingsSource

RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"
DEFAULT_RELAYMD_CONFIG_PATH = "~/.config/relaymd/config.yaml"


class CliSettings(BaseSettings):
    orchestrator_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices(
            "orchestrator_url",
            "RELAYMD_ORCHESTRATOR_URL",
        ),
    )
    api_token: str = Field(
        default="change-me",
        validation_alias=AliasChoices("api_token", "RELAYMD_API_TOKEN", "API_TOKEN"),
    )
    b2_endpoint_url: str = ""
    b2_bucket_name: str = ""
    b2_access_key_id: str = ""
    b2_secret_access_key: str = ""

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
            "orchestrator_url": ("RELAYMD_ORCHESTRATOR_URL",),
            "api_token": ("RELAYMD_API_TOKEN", "API_TOKEN"),
            "b2_endpoint_url": ("B2_ENDPOINT_URL",),
            "b2_bucket_name": ("B2_BUCKET_NAME",),
            "b2_access_key_id": ("B2_ACCESS_KEY_ID",),
            "b2_secret_access_key": ("B2_SECRET_ACCESS_KEY",),
        }
        raw_init_kwargs: object = getattr(yaml_source, "init_kwargs", None)
        if isinstance(raw_init_kwargs, dict):
            config_dicts = [raw_init_kwargs]
        elif isinstance(raw_init_kwargs, list):
            config_dicts = [item for item in raw_init_kwargs if isinstance(item, dict)]
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


def load_settings() -> CliSettings:
    return CliSettings()
