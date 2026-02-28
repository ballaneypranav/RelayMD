from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator
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
INFISICAL_BASE_URL = "https://app.infisical.com"
INFISICAL_WORKSPACE_ID = "dcf29082-7972-4bca-be58-363f6ad969c0"
INFISICAL_ENVIRONMENT = "prod"
INFISICAL_SECRET_PATH = "/RelayMD"


class ClusterConfig(BaseModel):
    name: str
    partition: str
    account: str
    gpu_type: str
    gpu_count: int
    strategy: Literal["reactive", "continuous", "jit_threshold"] = "reactive"
    sif_path: str | None = None
    image_uri: str | None = None
    nodes: int | None = Field(default=None, ge=1)
    ntasks: int | None = Field(default=None, ge=1)
    qos: str | None = None
    gres: str | None = None
    memory: str | None = None
    memory_per_gpu: str | None = None
    max_pending_jobs: int = 1
    wall_time: str = "4:00:00"

    @model_validator(mode="after")
    def _validate_image_source(self) -> ClusterConfig:
        has_sif_path = bool(self.sif_path and self.sif_path.strip())
        has_image_uri = bool(self.image_uri and self.image_uri.strip())
        if has_sif_path == has_image_uri:
            raise ValueError("set exactly one of 'sif_path' or 'image_uri'")

        if self.memory is not None:
            self.memory = self.memory.strip() or None
        if self.memory_per_gpu is not None:
            self.memory_per_gpu = self.memory_per_gpu.strip() or None
        if self.qos is not None:
            self.qos = self.qos.strip() or None
        if self.gres is not None:
            self.gres = self.gres.strip() or None

        if self.memory and self.memory_per_gpu:
            raise ValueError("set at most one of 'memory' or 'memory_per_gpu'")
        return self

    @property
    def apptainer_image(self) -> str:
        if self.sif_path and self.sif_path.strip():
            return self.sif_path
        if self.image_uri is None:
            raise ValueError("image_uri is required when sif_path is unset")
        image_uri = self.image_uri.strip()
        if "://" in image_uri:
            return image_uri
        return f"docker://{image_uri}"

    @property
    def slurm_gres(self) -> str:
        if self.gres:
            return self.gres
        return f"gpu:{self.gpu_type}:{self.gpu_count}"


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
    apptainer_docker_username: str = Field(
        default="",
        validation_alias=AliasChoices(
            "apptainer_docker_username",
            "APPTAINER_DOCKER_USERNAME",
            "SINGULARITY_DOCKER_USERNAME",
            "GHCR_USERNAME",
        ),
    )
    apptainer_docker_password: str = Field(
        default="",
        validation_alias=AliasChoices(
            "apptainer_docker_password",
            "APPTAINER_DOCKER_PASSWORD",
            "SINGULARITY_DOCKER_PASSWORD",
            "GHCR_PAT",
            "GHCR_TOKEN",
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
                "apptainer_docker_username": (
                    "APPTAINER_DOCKER_USERNAME",
                    "SINGULARITY_DOCKER_USERNAME",
                    "GHCR_USERNAME",
                ),
                "apptainer_docker_password": (
                    "APPTAINER_DOCKER_PASSWORD",
                    "SINGULARITY_DOCKER_PASSWORD",
                    "GHCR_PAT",
                    "GHCR_TOKEN",
                ),
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


def load_settings() -> OrchestratorSettings:
    settings = OrchestratorSettings()
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
            "Install relaymd with Infisical support or provide required secrets via env/config."
        ) from exc

    return ClientSettings, InfisicalClient, GetSecretOptions


def _needs_infisical_secret_hydration(settings: OrchestratorSettings) -> bool:
    if settings.api_token.strip() in {"", "change-me"}:
        return True

    uses_registry_image = any(cluster.image_uri for cluster in settings.slurm_cluster_configs)
    if not uses_registry_image:
        return False
    if not settings.apptainer_docker_username.strip():
        return True
    return bool(not settings.apptainer_docker_password.strip())


def _hydrate_settings_from_infisical(settings: OrchestratorSettings) -> OrchestratorSettings:
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
            "apptainer_docker_username": get("APPTAINER_DOCKER_USERNAME"),
            "apptainer_docker_password": get("APPTAINER_DOCKER_PASSWORD"),
        }
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to load orchestrator settings from Infisical") from exc

    updates: dict[str, str] = {}
    if settings.api_token.strip() in {"", "change-me"} and infisical_values["api_token"].strip():
        updates["api_token"] = infisical_values["api_token"]

    uses_registry_image = any(cluster.image_uri for cluster in settings.slurm_cluster_configs)
    if uses_registry_image:
        if (
            not settings.apptainer_docker_username.strip()
            and infisical_values["apptainer_docker_username"].strip()
        ):
            updates["apptainer_docker_username"] = infisical_values["apptainer_docker_username"]
        if (
            not settings.apptainer_docker_password.strip()
            and infisical_values["apptainer_docker_password"].strip()
        ):
            updates["apptainer_docker_password"] = infisical_values["apptainer_docker_password"]

    if not updates:
        return settings
    return settings.model_copy(update=updates)
