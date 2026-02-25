from __future__ import annotations

from relaymd.orchestrator import config as orchestrator_config
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings


def test_loads_yaml_config_from_relaymd_config_path(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "database_url: sqlite+aiosqlite:////tmp/relaymd.db",
                "api_token: yaml-token",
                "infisical_token: yaml-infisical",
                "heartbeat_timeout_multiplier: 2.5",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    gpu_count: 1",
                "    sif_path: /shared/containers/relaymd.sif",
                '    wall_time: "4:00:00"',
                "    max_pending_jobs: 2",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.delenv("RELAYMD_INFISICAL_TOKEN", raising=False)

    settings = OrchestratorSettings()

    assert settings.database_url == "sqlite+aiosqlite:////tmp/relaymd.db"
    assert settings.api_token == "yaml-token"
    assert settings.infisical_token == "yaml-infisical"
    assert settings.heartbeat_timeout_multiplier == 2.5
    assert settings.slurm_cluster_configs == [
        ClusterConfig(
            name="gilbreth-a30",
            partition="a30",
            account="my-account",
            gpu_type="a30",
            gpu_count=1,
            sif_path="/shared/containers/relaymd.sif",
            wall_time="4:00:00",
            max_pending_jobs=2,
        )
    ]


def test_missing_yaml_path_is_non_fatal(monkeypatch, tmp_path) -> None:
    missing_config_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("RELAYMD_CONFIG", str(missing_config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    settings = OrchestratorSettings()

    assert settings.database_url == "sqlite+aiosqlite:///./relaymd.db"


def test_env_secret_overrides_yaml_value(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_token: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-token")

    settings = OrchestratorSettings()

    assert settings.api_token == "env-token"


def test_env_secret_overrides_yaml_alias_key(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("RELAYMD_API_TOKEN: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("API_TOKEN", "env-token")

    settings = OrchestratorSettings()

    assert settings.api_token == "env-token"


def test_cwd_config_overrides_home_config(monkeypatch, tmp_path) -> None:
    home_config = tmp_path / "home-config.yaml"
    home_config.write_text("api_token: home-token\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(orchestrator_config, "DEFAULT_RELAYMD_CONFIG_PATH", str(home_config))
    monkeypatch.chdir(cwd_dir)

    settings = OrchestratorSettings()

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

    settings = OrchestratorSettings()

    assert settings.api_token == "explicit-token"
