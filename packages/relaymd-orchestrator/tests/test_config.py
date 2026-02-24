from __future__ import annotations

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

    settings = OrchestratorSettings()

    assert settings.database_url == "sqlite+aiosqlite:///./relaymd.db"


def test_env_secret_overrides_yaml_value(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_token: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-token")

    settings = OrchestratorSettings()

    assert settings.api_token == "env-token"
