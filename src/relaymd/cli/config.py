from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from pydantic_settings.sources import PydanticBaseSettingsSource

from relaymd.core_secret_management import CliSecretManager
from relaymd.runtime_defaults import (
    DEFAULT_CF_WORKER_URL,
    DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
    DEFAULT_ORCHESTRATOR_URL,
)
from relaymd.settings_sources import relaymd_config_paths, relaymd_settings_sources

RELAYMD_CONFIG_ENV_VAR = "RELAYMD_CONFIG"
DEFAULT_RELAYMD_CONFIG_PATH = "~/.config/relaymd/config.yaml"
INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "prod"
INFISICAL_SECRET_PATH = "/RelayMD"


class CliSettings(BaseSettings):
    storage_provider: Literal["cloudflare_backblaze", "purdue"] = Field(
        default="cloudflare_backblaze",
        validation_alias=AliasChoices("storage_provider"),
    )
    orchestrator_url: str = Field(
        default=DEFAULT_ORCHESTRATOR_URL,
        validation_alias=AliasChoices(
            "orchestrator_url",
            "RELAYMD_ORCHESTRATOR_URL",
        ),
    )
    api_token: str = Field(
        default="",
        validation_alias=AliasChoices("api_token"),
    )
    infisical_token: str = Field(
        default="",
        validation_alias=AliasChoices("infisical_token", "INFISICAL_TOKEN"),
    )
    b2_endpoint_url: str = Field(
        default="",
        validation_alias=AliasChoices("b2_endpoint_url"),
    )
    b2_bucket_name: str = Field(
        default="",
        validation_alias=AliasChoices("b2_bucket_name"),
    )
    b2_access_key_id: str = Field(
        default="",
        validation_alias=AliasChoices("b2_access_key_id"),
    )
    b2_secret_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("b2_secret_access_key"),
    )
    cf_worker_url: str = Field(
        default=DEFAULT_CF_WORKER_URL,
        validation_alias=AliasChoices("cf_worker_url", "CF_WORKER_URL"),
    )
    cf_bearer_token: str = Field(
        default="",
        validation_alias=AliasChoices("cf_bearer_token"),
    )
    purdue_s3_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("purdue_s3_endpoint"),
    )
    purdue_s3_bucket_name: str = Field(
        default="",
        validation_alias=AliasChoices("purdue_s3_bucket_name"),
    )
    purdue_s3_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("purdue_s3_access_key"),
    )
    purdue_s3_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("purdue_s3_secret_key"),
    )
    purdue_s3_user: str = Field(
        default="",
        validation_alias=AliasChoices("purdue_s3_user"),
    )
    orchestrator_timeout_seconds: float = Field(
        default=DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS,
        validation_alias=AliasChoices(
            "orchestrator_timeout_seconds",
            "ORCHESTRATOR_TIMEOUT_SECONDS",
            "RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS",
        ),
    )

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
                "infisical_token": ("INFISICAL_TOKEN",),
                "orchestrator_url": ("RELAYMD_ORCHESTRATOR_URL",),
                "cf_worker_url": ("CF_WORKER_URL",),
                "orchestrator_timeout_seconds": (
                    "ORCHESTRATOR_TIMEOUT_SECONDS",
                    "RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS",
                ),
            },
            config_paths=cls.config_paths(),
            yaml_env_only_fields={"infisical_token"},
        )


def load_settings() -> CliSettings:
    settings = CliSettings()
    if not settings.infisical_token.strip():
        raise RuntimeError(
            "INFISICAL_TOKEN is required. RelayMD secret values are sourced from Infisical."
        )

    settings = _hydrate_settings_from_infisical(settings)

    missing: list[str] = []
    if not settings.api_token.strip():
        missing.append("RELAYMD_API_TOKEN")
    if settings.storage_provider == "purdue":
        if not settings.purdue_s3_endpoint.strip():
            missing.append("PURDUE_S3_ENDPOINT")
        if not settings.purdue_s3_bucket_name.strip():
            missing.append("PURDUE_S3_BUCKET_NAME")
        if not settings.purdue_s3_access_key.strip():
            missing.append("PURDUE_S3_ACCESS_KEY")
        if not settings.purdue_s3_secret_key.strip():
            missing.append("PURDUE_S3_SECRET_KEY")
    else:
        if not settings.b2_endpoint_url.strip():
            missing.append("B2_ENDPOINT")
        if not settings.b2_bucket_name.strip():
            missing.append("BUCKET_NAME")
        if not settings.b2_access_key_id.strip():
            missing.append("B2_APPLICATION_KEY_ID")
        if not settings.b2_secret_access_key.strip():
            missing.append("B2_APPLICATION_KEY")

    if missing:
        raise RuntimeError(
            "Missing required configuration properties after secret hydration. "
            f"Please ensure Infisical is properly configured for: {', '.join(missing)}"
        )

    return settings


def _get_infisical_client_dependencies() -> tuple[type[Any], type[Any], type[Any]]:
    try:
        from infisical_client import ClientSettings, InfisicalClient
        from infisical_client.schemas import GetSecretOptions
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "INFISICAL_TOKEN is set but infisical-python is not installed. "
            "Install relaymd with Infisical support or provide B2 settings via env/config."
        ) from exc

    return ClientSettings, InfisicalClient, GetSecretOptions


def _hydrate_settings_from_infisical(settings: CliSettings) -> CliSettings:
    try:
        secret_manager = CliSecretManager(
            machine_token=settings.infisical_token,
            dependency_loader=_get_infisical_client_dependencies,
            base_url=INFISICAL_BASE_URL,
            workspace_id=INFISICAL_WORKSPACE_ID,
            environment=INFISICAL_ENVIRONMENT,
            secret_path=INFISICAL_SECRET_PATH,
        )
        infisical_values = secret_manager.fetch_settings_values()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "Invalid credentials" in msg or "invalid credentials" in msg:
            raise RuntimeError(
                "Infisical authentication failed: INFISICAL_TOKEN is invalid or expired. "
                "Rotate your machine identity token in the Infisical dashboard "
                "and update INFISICAL_TOKEN in your env file."
            ) from exc
        raise RuntimeError(f"Failed to load CLI settings from Infisical: {msg}") from exc

    updates = {k: v for k, v in infisical_values.items() if v.strip()}
    if not updates:
        return settings
    return settings.model_copy(update=updates)
