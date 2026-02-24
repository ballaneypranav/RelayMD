from __future__ import annotations

from relaymd.cli.config import CliSettings


def test_relaymd_orchestrator_url_env_override(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_ORCHESTRATOR_URL", "https://orchestrator.example")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.orchestrator_url == "https://orchestrator.example"
