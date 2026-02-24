from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./relaymd.db"
    api_token: str = "change-me"
    heartbeat_timeout_multiplier: float = 2.0

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
