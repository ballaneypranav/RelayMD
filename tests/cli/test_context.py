from __future__ import annotations

from relaymd.cli import context as cli_context
from relaymd.cli.config import CliSettings


def _settings(**overrides: object) -> CliSettings:
    base: dict[str, object] = {
        "orchestrator_url": "https://orchestrator.example/",
        "orchestrator_timeout_seconds": 17.5,
        "api_token": "test-token",
        "b2_endpoint_url": "https://b2.example",
        "b2_bucket_name": "bucket",
        "b2_access_key_id": "access",
        "b2_secret_access_key": "secret",
        "cf_worker_url": "https://cf.example",
        "cf_bearer_token": "token",
    }
    base.update(overrides)
    return CliSettings.model_validate(base)


def test_api_client_uses_trimmed_base_url_and_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeApiClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(cli_context.httpx, "Timeout", lambda value: ("timeout", value))
    monkeypatch.setattr(cli_context, "RelaymdApiClient", FakeApiClient)

    context = cli_context.CliContext(settings=_settings())
    client = context.api_client()

    assert isinstance(client, FakeApiClient)
    assert captured["base_url"] == "https://orchestrator.example"
    assert captured["timeout"] == ("timeout", 17.5)
    assert captured["raise_on_unexpected_status"] is True


def test_storage_client_uses_configured_credentials(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeStorageClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(cli_context, "StorageClient", FakeStorageClient)

    context = cli_context.CliContext(settings=_settings())
    storage = context.storage_client()

    assert isinstance(storage, FakeStorageClient)
    assert captured == {
        "b2_endpoint_url": "https://b2.example",
        "b2_bucket_name": "bucket",
        "b2_access_key_id": "access",
        "b2_secret_access_key": "secret",
        "cf_worker_url": "https://cf.example",
        "cf_bearer_token": "token",
    }


def test_create_cli_context_uses_explicit_settings() -> None:
    settings = _settings()

    context = cli_context.create_cli_context(settings=settings)

    assert context.settings is settings


def test_create_cli_context_loads_settings_when_not_provided(monkeypatch) -> None:
    settings = _settings()
    monkeypatch.setattr(cli_context, "load_settings", lambda: settings)

    context = cli_context.create_cli_context()

    assert context.settings is settings
