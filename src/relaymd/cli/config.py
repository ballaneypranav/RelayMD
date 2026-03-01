from __future__ import annotations

from pathlib import Path
from typing import Any

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
INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "prod"
INFISICAL_SECRET_PATH = "/RelayMD"


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
    infisical_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "infisical_token",
            "INFISICAL_TOKEN",
            "RELAYMD_INFISICAL_TOKEN",
        ),
    )
    b2_endpoint_url: str = Field(
        default="",
        validation_alias=AliasChoices("b2_endpoint_url", "B2_ENDPOINT_URL", "B2_ENDPOINT"),
    )
    b2_bucket_name: str = Field(
        default="",
        validation_alias=AliasChoices("b2_bucket_name", "B2_BUCKET_NAME", "BUCKET_NAME"),
    )
    b2_access_key_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "b2_access_key_id",
            "B2_ACCESS_KEY_ID",
            "B2_APPLICATION_KEY_ID",
        ),
    )
    b2_secret_access_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "b2_secret_access_key",
            "B2_SECRET_ACCESS_KEY",
            "B2_APPLICATION_KEY",
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
                "api_token": ("RELAYMD_API_TOKEN", "API_TOKEN"),
                "infisical_token": ("INFISICAL_TOKEN", "RELAYMD_INFISICAL_TOKEN"),
                "b2_endpoint_url": ("B2_ENDPOINT_URL", "B2_ENDPOINT"),
                "b2_bucket_name": ("B2_BUCKET_NAME", "BUCKET_NAME"),
                "b2_access_key_id": ("B2_ACCESS_KEY_ID", "B2_APPLICATION_KEY_ID"),
                "b2_secret_access_key": ("B2_SECRET_ACCESS_KEY", "B2_APPLICATION_KEY"),
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
    settings = CliSettings()
    return _hydrate_settings_from_infisical(settings)


def _parse_infisical_machine_token(raw_token: str) -> tuple[str, str]:
    if ":" not in raw_token:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected format <client_id>:<client_secret>"
        )

    client_id, client_secret = raw_token.split(":", 1)
    if not client_id or not client_secret:
        raise RuntimeError(
            "INFISICAL_TOKEN is malformed; expected non-empty <client_id>:<client_secret>"
        )
    return client_id, client_secret


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


def _needs_infisical_secret_hydration(settings: CliSettings) -> bool:
    if settings.api_token.strip() in {"", "change-me"}:
        return True
    if not settings.b2_endpoint_url.strip():
        return True
    if not settings.b2_bucket_name.strip():
        return True
    if not settings.b2_access_key_id.strip():
        return True
    return bool(not settings.b2_secret_access_key.strip())


def _hydrate_settings_from_infisical(settings: CliSettings) -> CliSettings:
    if not settings.infisical_token.strip():
        return settings
    if not _needs_infisical_secret_hydration(settings):
        return settings

    ClientSettings, InfisicalClient, GetSecretOptions = _get_infisical_client_dependencies()
    client_id, client_secret = _parse_infisical_machine_token(settings.infisical_token)

    try:
        client = InfisicalClient(
            settings=ClientSettings(
                client_id=client_id,
                client_secret=client_secret,
                site_url=INFISICAL_BASE_URL,
            )
        )

        def get(name: str) -> str:
            return client.getSecret(
                GetSecretOptions(
                    secret_name=name,
                    project_id=INFISICAL_WORKSPACE_ID,
                    environment=INFISICAL_ENVIRONMENT,
                    path=INFISICAL_SECRET_PATH,
                )
            ).secret_value

        infisical_values = {
            "api_token": get("RELAYMD_API_TOKEN"),
            "b2_endpoint_url": get("B2_ENDPOINT"),
            "b2_bucket_name": get("BUCKET_NAME"),
            "b2_access_key_id": get("B2_APPLICATION_KEY_ID"),
            "b2_secret_access_key": get("B2_APPLICATION_KEY"),
        }
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "Invalid credentials" in msg or "invalid credentials" in msg:
            raise RuntimeError(
                "Infisical authentication failed: the token in 'infisical_token' is invalid "
                "or expired. Rotate your machine identity token in the Infisical dashboard "
                "and update the INFISICAL_TOKEN env var or 'infisical_token' in your config."
            ) from exc
        raise RuntimeError(f"Failed to load CLI settings from Infisical: {msg}") from exc

    updates: dict[str, str] = {}
    if settings.api_token.strip() in {"", "change-me"} and infisical_values["api_token"].strip():
        updates["api_token"] = infisical_values["api_token"]
    if not settings.b2_endpoint_url.strip() and infisical_values["b2_endpoint_url"].strip():
        updates["b2_endpoint_url"] = infisical_values["b2_endpoint_url"]
    if not settings.b2_bucket_name.strip() and infisical_values["b2_bucket_name"].strip():
        updates["b2_bucket_name"] = infisical_values["b2_bucket_name"]
    if not settings.b2_access_key_id.strip() and infisical_values["b2_access_key_id"].strip():
        updates["b2_access_key_id"] = infisical_values["b2_access_key_id"]
    if (
        not settings.b2_secret_access_key.strip()
        and infisical_values["b2_secret_access_key"].strip()
    ):
        updates["b2_secret_access_key"] = infisical_values["b2_secret_access_key"]

    if not updates:
        return settings
    return settings.model_copy(update=updates)
