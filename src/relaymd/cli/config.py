from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from pydantic_settings.sources import PydanticBaseSettingsSource

from relaymd.runtime_defaults import (
    DEFAULT_CF_WORKER_URL,
    DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    DEFAULT_ORCHESTRATOR_URL,
)
from relaymd.settings_sources import relaymd_config_paths, relaymd_settings_sources

RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"
DEFAULT_RELAYMD_CONFIG_PATH = "~/.config/relaymd/config.yaml"


class CliSettings(BaseSettings):
    orchestrator_url: str = Field(
        default=DEFAULT_ORCHESTRATOR_URL,
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
    cf_worker_url: str = DEFAULT_CF_WORKER_URL
    cf_bearer_token: str = ""
    orchestrator_timeout_seconds: float = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS

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
                "orchestrator_url": ("RELAYMD_ORCHESTRATOR_URL",),
                "api_token": ("RELAYMD_API_TOKEN", "API_TOKEN"),
                "b2_endpoint_url": ("B2_ENDPOINT_URL",),
                "b2_bucket_name": ("B2_BUCKET_NAME",),
                "b2_access_key_id": ("B2_ACCESS_KEY_ID",),
                "b2_secret_access_key": ("B2_SECRET_ACCESS_KEY",),
                "cf_worker_url": ("CF_WORKER_URL",),
                "cf_bearer_token": ("CF_BEARER_TOKEN", "DOWNLOAD_BEARER_TOKEN"),
                "orchestrator_timeout_seconds": (
                    "ORCHESTRATOR_TIMEOUT_SECONDS",
                    "RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS",
                ),
            },
            config_paths=cls.config_paths(),
        )


def load_settings() -> CliSettings:
    return CliSettings()
