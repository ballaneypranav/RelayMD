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
