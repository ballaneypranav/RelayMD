from __future__ import annotations

import pytest
from pydantic import ValidationError
from relaymd.worker.config import WorkerRuntimeSettings


def test_storage_provider_defaults_to_purdue(monkeypatch) -> None:
    monkeypatch.delenv("RELAYMD_STORAGE_PROVIDER", raising=False)
    settings = WorkerRuntimeSettings(worker_image_key="atom-openmm")
    assert settings.storage_provider == "purdue"


def test_relaymd_storage_provider_env_override(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_STORAGE_PROVIDER", "cloudflare_backblaze")
    settings = WorkerRuntimeSettings(worker_image_key="atom-openmm")
    assert settings.storage_provider == "cloudflare_backblaze"


def test_heartbeat_failure_grace_defaults() -> None:
    settings = WorkerRuntimeSettings(worker_image_key="atom-openmm")
    assert settings.heartbeat_failure_grace_multiplier == 15
    assert settings.heartbeat_failure_grace_floor_seconds == 900


def test_heartbeat_failure_grace_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER", "7")
    monkeypatch.setenv("RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS", "120")
    settings = WorkerRuntimeSettings(worker_image_key="atom-openmm")
    assert settings.heartbeat_failure_grace_multiplier == 7
    assert settings.heartbeat_failure_grace_floor_seconds == 120


def test_worker_image_key_is_required(monkeypatch) -> None:
    monkeypatch.delenv("RELAYMD_WORKER_IMAGE_KEY", raising=False)

    with pytest.raises(ValidationError, match="worker_image_key"):
        WorkerRuntimeSettings.model_validate({})
