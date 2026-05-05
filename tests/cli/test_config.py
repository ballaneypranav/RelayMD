from __future__ import annotations

import pytest

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
        "orchestrator_url: http://127.0.0.1:36158\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.setenv("RELAYMD_ORCHESTRATOR_URL", "https://orchestrator.example")
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.orchestrator_url == "https://orchestrator.example"


def test_download_bearer_token_alias_env(monkeypatch) -> None:
    monkeypatch.setenv("DOWNLOAD_BEARER_TOKEN", "download-token")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.cf_bearer_token == ""


def test_relaymd_cli_timeout_alias_env(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")

    settings = CliSettings()

    assert settings.orchestrator_timeout_seconds == 45


def test_infisical_token_yaml_key_is_ignored(monkeypatch, tmp_path) -> None:
    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text(
        "infisical_token: yaml-token\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.infisical_token == ""


def test_b2_yaml_values_not_overridden_by_non_aliased_env(monkeypatch, tmp_path) -> None:
    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text(
        "\n".join(
            [
                "b2_endpoint_url: https://yaml.endpoint",
                "b2_bucket_name: yaml-bucket",
                "b2_access_key_id: yaml-access",
                "b2_secret_access_key: yaml-secret",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_DATA_ROOT", raising=False)
    monkeypatch.setenv("B2_ENDPOINT", "https://env.endpoint")
    monkeypatch.setenv("BUCKET_NAME", "env-bucket")
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "env-access")
    monkeypatch.setenv("B2_APPLICATION_KEY", "env-secret")
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.b2_endpoint_url == "https://yaml.endpoint"
    assert settings.b2_bucket_name == "yaml-bucket"
    assert settings.b2_access_key_id == "yaml-access"
    assert settings.b2_secret_access_key == "yaml-secret"


def test_cwd_config_overrides_home_config(monkeypatch, tmp_path) -> None:
    home_config = tmp_path / "home-config.yaml"
    home_config.write_text("api_token: home-token\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_DATA_ROOT", raising=False)
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


def test_data_root_sets_default_config_path(monkeypatch, tmp_path) -> None:
    data_root = tmp_path / "relaymd-service"
    config_dir = data_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "relaymd-config.yaml").write_text(
        "api_token: data-root-token\n",
        encoding="utf-8",
    )

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.chdir(cwd_dir)

    settings = CliSettings()

    assert settings.api_token == "data-root-token"


def test_load_settings_hydrates_missing_values_from_infisical(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("B2_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("B2_ENDPOINT", raising=False)
    monkeypatch.delenv("B2_BUCKET_NAME", raising=False)
    monkeypatch.delenv("BUCKET_NAME", raising=False)
    monkeypatch.delenv("B2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY_ID", raising=False)
    monkeypatch.delenv("B2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)

    values = {
        "RELAYMD_API_TOKEN": "relaymd-token",
        "B2_ENDPOINT": "https://s3.us-east-005.backblazeb2.com",
        "BUCKET_NAME": "relaymd-bucket",
        "B2_APPLICATION_KEY_ID": "key-id",
        "B2_APPLICATION_KEY": "key-secret",
    }
    secret_calls: list[str] = []

    class _FakeClientSettings:
        def __init__(self, client_id: str, client_secret: str, site_url: str) -> None:
            self.client_id = client_id
            self.client_secret = client_secret
            self.site_url = site_url

    class _FakeGetSecretOptions:
        def __init__(
            self,
            *,
            secret_name: str,
            project_id: str,
            environment: str,
            path: str,
        ) -> None:
            self.secret_name = secret_name
            self.project_id = project_id
            self.environment = environment
            self.path = path

    class _FakeSecret:
        def __init__(self, secret_value: str) -> None:
            self.secret_value = secret_value

    class _FakeInfisicalClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        def getSecret(self, options) -> _FakeSecret:
            secret_calls.append(options.secret_name)
            try:
                return _FakeSecret(values[options.secret_name])
            except KeyError as exc:
                raise Exception("Secret not found") from exc

    monkeypatch.setattr(
        cli_config,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = cli_config.load_settings()

    assert settings.api_token == "relaymd-token"
    assert settings.b2_endpoint_url == "https://s3.us-east-005.backblazeb2.com"
    assert settings.b2_bucket_name == "relaymd-bucket"
    assert settings.b2_access_key_id == "key-id"
    assert settings.b2_secret_access_key == "key-secret"
    assert secret_calls == [
        "RELAYMD_API_TOKEN",
        "B2_ENDPOINT",
        "BUCKET_NAME",
        "B2_APPLICATION_KEY_ID",
        "B2_APPLICATION_KEY",
        "DOWNLOAD_BEARER_TOKEN",
    ]


def test_load_settings_infisical_values_win_over_env(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-relay-token")
    monkeypatch.setenv("B2_ENDPOINT_URL", "https://env.endpoint")
    monkeypatch.setenv("B2_BUCKET_NAME", "env-bucket")
    monkeypatch.setenv("B2_ACCESS_KEY_ID", "env-access")
    monkeypatch.setenv("B2_SECRET_ACCESS_KEY", "env-secret")

    values = {
        "RELAYMD_API_TOKEN": "infisical-relay-token",
        "B2_ENDPOINT": "https://infisical.endpoint",
        "BUCKET_NAME": "infisical-bucket",
        "B2_APPLICATION_KEY_ID": "infisical-access",
        "B2_APPLICATION_KEY": "infisical-secret",
    }

    class _FakeClientSettings:
        def __init__(self, client_id: str, client_secret: str, site_url: str) -> None:
            self.client_id = client_id
            self.client_secret = client_secret
            self.site_url = site_url

    class _FakeGetSecretOptions:
        def __init__(
            self,
            *,
            secret_name: str,
            project_id: str,
            environment: str,
            path: str,
        ) -> None:
            self.secret_name = secret_name
            self.project_id = project_id
            self.environment = environment
            self.path = path

    class _FakeSecret:
        def __init__(self, secret_value: str) -> None:
            self.secret_value = secret_value

    class _FakeInfisicalClient:
        def __init__(self, settings) -> None:
            self.settings = settings

        def getSecret(self, options) -> _FakeSecret:
            try:
                return _FakeSecret(values[options.secret_name])
            except KeyError as exc:
                raise Exception("Secret not found") from exc

    monkeypatch.setattr(
        cli_config,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = cli_config.load_settings()

    assert settings.api_token == "infisical-relay-token"
    assert settings.b2_endpoint_url == "https://infisical.endpoint"
    assert settings.b2_bucket_name == "infisical-bucket"
    assert settings.b2_access_key_id == "infisical-access"
    assert settings.b2_secret_access_key == "infisical-secret"


def test_load_settings_malformed_infisical_token_raises(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")
    monkeypatch.setenv("INFISICAL_TOKEN", "malformed-token")
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("B2_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("B2_ENDPOINT", raising=False)
    monkeypatch.delenv("B2_BUCKET_NAME", raising=False)
    monkeypatch.delenv("BUCKET_NAME", raising=False)
    monkeypatch.delenv("B2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY_ID", raising=False)
    monkeypatch.delenv("B2_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)

    with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is malformed"):
        cli_config.load_settings()
