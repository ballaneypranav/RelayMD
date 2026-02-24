from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    api_token: str = "change-me"
    heartbeat_timeout_multiplier: float = 2.0
    infisical_token: str = ""
    slurm_cluster_configs: list[ClusterConfig] = []

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
