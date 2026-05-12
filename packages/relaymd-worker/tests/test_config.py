from __future__ import annotations

from relaymd.worker.config import WorkerRuntimeSettings


def test_storage_provider_defaults_to_purdue(monkeypatch) -> None:
    monkeypatch.delenv("RELAYMD_STORAGE_PROVIDER", raising=False)
    settings = WorkerRuntimeSettings()
    assert settings.storage_provider == "purdue"


def test_relaymd_storage_provider_env_override(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_STORAGE_PROVIDER", "cloudflare_backblaze")
    settings = WorkerRuntimeSettings()
    assert settings.storage_provider == "cloudflare_backblaze"


def test_heartbeat_failure_grace_defaults() -> None:
    settings = WorkerRuntimeSettings()
    assert settings.heartbeat_failure_grace_multiplier == 15
    assert settings.heartbeat_failure_grace_floor_seconds == 900


def test_heartbeat_failure_grace_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER", "7")
    monkeypatch.setenv("RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS", "120")
    settings = WorkerRuntimeSettings()
    assert settings.heartbeat_failure_grace_multiplier == 7
    assert settings.heartbeat_failure_grace_floor_seconds == 120
