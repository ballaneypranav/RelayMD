from __future__ import annotations

from relaymd.cli import config as cli_config
from relaymd.cli.config import CliSettings


def test_relaymd_orchestrator_url_env_override(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_ORCHESTRATOR_URL", "https://orchestrator.example")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.orchestrator_url == "https://orchestrator.example"


def test_yaml_orchestrator_url_overrides_env(monkeypatch, tmp_path) -> None:
    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text(
        "orchestrator_url: http://127.0.0.1:8000\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.setenv("RELAYMD_ORCHESTRATOR_URL", "https://orchestrator.example")
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.orchestrator_url == "http://127.0.0.1:8000"


def test_download_bearer_token_alias_env(monkeypatch) -> None:
    monkeypatch.setenv("DOWNLOAD_BEARER_TOKEN", "download-token")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.cf_bearer_token == "download-token"


def test_relaymd_cli_timeout_alias_env(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.orchestrator_timeout_seconds == 45


def test_cwd_config_overrides_home_config(monkeypatch, tmp_path) -> None:
    home_config = tmp_path / "home-config.yaml"
    home_config.write_text("api_token: home-token\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(cli_config, "DEFAULT_RELAYMD_CONFIG_PATH", str(home_config))
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.api_token == "cwd-token"


def test_explicit_relaymd_config_env_skips_cwd(monkeypatch, tmp_path) -> None:
    explicit_config = tmp_path / "explicit-config.yaml"
    explicit_config.write_text("api_token: explicit-token\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.setenv("RELAYMD_CONFIG", str(explicit_config))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.api_token == "explicit-token"
