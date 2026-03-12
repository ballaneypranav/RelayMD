from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator
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
from relaymd.secret_management import OrchestratorSecretManager
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
    extends: str | None = None
    is_template: bool = False
    ssh_host: str
    ssh_username: str
    ssh_key_file: str | None = None
    ssh_port: int = 22
    gpu_type: str = "unknown"
    gpu_count: int = 0
    strategy: Literal["reactive", "continuous", "jit_threshold"] = "reactive"
    jit_threshold_hours: float = Field(default=6.0, gt=0)
    sif_path: str | None = None
    image_uri: str | None = None
    nodes: int | None = Field(default=None, ge=1)
    ntasks: int | None = Field(default=None, ge=1)
    qos: str | None = None
    gres: str | None = None
    memory: str | None = None
    memory_per_gpu: str | None = None
    idle_strategy: Literal["immediate_exit", "poll_then_exit"] | None = None
    idle_poll_interval_seconds: int | None = Field(default=None, ge=1)
    idle_poll_max_seconds: int | None = Field(default=None, ge=1)
    max_pending_jobs: int = 1
    wall_time: str = "4:00:00"
    log_directory: str | None = None

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
    log_directory: str | None = Field(
        default=None,
        validation_alias=AliasChoices("log_directory", "RELAYMD_LOG_DIRECTORY"),
    )
    api_token: str = Field(
        default="",
        validation_alias=AliasChoices("api_token"),
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
    worker_idle_strategy: Literal["immediate_exit", "poll_then_exit"] = "immediate_exit"
    worker_idle_poll_interval_seconds: int = 30
    worker_idle_poll_max_seconds: int = 600
    infisical_token: str = Field(
        default="",
        validation_alias=AliasChoices("infisical_token", "INFISICAL_TOKEN"),
    )
    apptainer_docker_username: str = Field(default="")
    apptainer_docker_password: str = Field(default="")
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
    tailscale_socket: str = Field(
        default="~/.tailscale/tailscaled.sock",
        validation_alias=AliasChoices("tailscale_socket", "RELAYMD_TAILSCALE_SOCKET"),
    )
    axiom_token: str = Field(
        default="",
        validation_alias=AliasChoices("axiom_token"),
    )
    axiom_dataset: str = Field(
        default="relaymd",
        validation_alias=AliasChoices("axiom_dataset", "AXIOM_DATASET", "RELAYMD_AXIOM_DATASET"),
    )
    tailscale_auth_key: str = Field(default="")
    tailscale_hostname: str = Field(
        default="relaymd-orchestrator",
        validation_alias=AliasChoices("tailscale_hostname", "RELAYMD_TAILSCALE_HOSTNAME"),
    )

    @field_validator("slurm_cluster_configs", mode="before")
    @classmethod
    def _resolve_slurm_cluster_configs(
        cls, raw_cluster_configs: Any
    ) -> list[dict[str, Any]] | list[ClusterConfig]:
        if not isinstance(raw_cluster_configs, list):
            return raw_cluster_configs

        by_name: dict[str, dict[str, Any]] = {}
        cluster_order: list[str] = []

        for index, raw_cluster in enumerate(raw_cluster_configs):
            if isinstance(raw_cluster, ClusterConfig):
                cluster_name = raw_cluster.name
                raw_cluster_dict = raw_cluster.model_dump()
            elif isinstance(raw_cluster, dict):
                cluster_name_value = raw_cluster.get("name")
                if not isinstance(cluster_name_value, str) or not cluster_name_value.strip():
                    raise ValueError(
                        f"slurm_cluster_configs[{index}].name must be a non-empty string"
                    )
                cluster_name = cluster_name_value.strip()
                raw_cluster_dict = dict(raw_cluster)
                raw_cluster_dict["name"] = cluster_name
            else:
                raw_type_name = type(raw_cluster).__name__
                raise ValueError(
                    f"slurm_cluster_configs[{index}] must be a mapping, got {raw_type_name}"
                )

            if cluster_name in by_name:
                raise ValueError(f"duplicate slurm cluster config name: {cluster_name}")

            by_name[cluster_name] = raw_cluster_dict
            cluster_order.append(cluster_name)

        resolved: dict[str, dict[str, Any]] = {}
        resolution_stack: list[str] = []
        resolving: set[str] = set()

        def _resolve(name: str) -> dict[str, Any]:
            if name in resolved:
                return resolved[name]
            if name in resolving:
                cycle_start = resolution_stack.index(name)
                cycle = " -> ".join([*resolution_stack[cycle_start:], name])
                raise ValueError(f"cycle detected in slurm cluster inheritance: {cycle}")

            resolving.add(name)
            resolution_stack.append(name)
            raw_cluster = by_name[name]
            extends_raw = raw_cluster.get("extends")
            merged: dict[str, Any] = {}
            has_parent = False
            if extends_raw is not None:
                has_parent = True
                if not isinstance(extends_raw, str) or not extends_raw.strip():
                    raise ValueError(
                        f"slurm_cluster_configs[{name}].extends must be a non-empty string when set"
                    )
                parent_name = extends_raw.strip()
                if parent_name not in by_name:
                    raise ValueError(
                        f"slurm cluster '{name}' extends unknown cluster '{parent_name}'"
                    )
                merged.update(_resolve(parent_name))
                raw_cluster = dict(raw_cluster)
                raw_cluster["extends"] = parent_name

            merged.update(raw_cluster)
            merged["name"] = name
            if has_parent and "is_template" not in raw_cluster:
                merged["is_template"] = False

            partition = merged.get("partition")
            if isinstance(partition, list):
                raise ValueError(
                    "slurm cluster "
                    f"'{name}' has invalid partition list; "
                    "partition must be a single string"
                )

            resolution_stack.pop()
            resolving.remove(name)
            resolved[name] = merged
            return merged

        runtime_clusters: list[dict[str, Any]] = []
        for cluster_name in cluster_order:
            cluster = _resolve(cluster_name)
            if cluster.get("is_template", False):
                continue
            runtime_clusters.append(cluster)

        return runtime_clusters

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
                "log_directory": ("RELAYMD_LOG_DIRECTORY",),
                "infisical_token": ("INFISICAL_TOKEN",),
                "salad_api_key": ("SALAD_API_KEY",),
                "salad_org": ("SALAD_ORG",),
                "salad_project": ("SALAD_PROJECT",),
                "salad_container_group": ("SALAD_CONTAINER_GROUP",),
                "salad_max_replicas": ("SALAD_MAX_REPLICAS",),
                "sbatch_submit_timeout_seconds": ("SBATCH_SUBMIT_TIMEOUT_SECONDS",),
                "axiom_dataset": ("AXIOM_DATASET",),
            },
            config_paths=cls.config_paths(),
        )


def load_settings() -> OrchestratorSettings:
    settings = OrchestratorSettings()
    if not settings.infisical_token.strip():
        raise RuntimeError(
            "INFISICAL_TOKEN is required. RelayMD secret values are sourced from Infisical."
        )

    settings = _hydrate_settings_from_infisical(settings)

    missing = []
    if not settings.api_token.strip():
        missing.append("RELAYMD_API_TOKEN")
    if not settings.axiom_token.strip():
        missing.append("AXIOM_TOKEN")

    has_slurm = len(settings.slurm_cluster_configs) > 0
    has_salad = bool(
        settings.salad_api_key
        and settings.salad_org
        and settings.salad_project
        and settings.salad_container_group
    )
    if (has_slurm or has_salad) and not settings.tailscale_auth_key.strip():
        missing.append("TAILSCALE_AUTH_KEY")

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
            "Install relaymd with Infisical support or provide required secrets via env/config."
        ) from exc

    return ClientSettings, InfisicalClient, GetSecretOptions


def _hydrate_settings_from_infisical(settings: OrchestratorSettings) -> OrchestratorSettings:
    has_slurm = len(settings.slurm_cluster_configs) > 0
    has_salad = bool(
        settings.salad_api_key
        and settings.salad_org
        and settings.salad_project
        and settings.salad_container_group
    )
    try:
        secret_manager = OrchestratorSecretManager(
            machine_token=settings.infisical_token,
            dependency_loader=_get_infisical_client_dependencies,
            base_url=INFISICAL_BASE_URL,
            workspace_id=INFISICAL_WORKSPACE_ID,
            environment=INFISICAL_ENVIRONMENT,
            secret_path=INFISICAL_SECRET_PATH,
        )
        infisical_values = secret_manager.fetch_settings_values(
            include_tailscale_auth_key=(has_slurm or has_salad)
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to load orchestrator settings from Infisical") from exc

    updates = {k: v for k, v in infisical_values.items() if v.strip()}
    if not updates:
        return settings
    return settings.model_copy(update=updates)
