from __future__ import annotations

import pytest

from relaymd.orchestrator import config as orchestrator_config
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings, WorkerImageSource


def _worker_images(
    *,
    sif_path: str | None = None,
    image_uri: str | None = None,
    sif_cache_dir: str | None = None,
) -> dict[str, WorkerImageSource]:
    return {
        "atom-openmm": WorkerImageSource(
            sif_path=sif_path,
            image_uri=image_uri,
            sif_cache_dir=sif_cache_dir,
        )
    }


def test_loads_yaml_config_from_relaymd_config_path(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "database_url: sqlite+aiosqlite:////tmp/relaymd.db",
                "log_directory: /tmp/relaymd-logs",
                "api_token: yaml-token",
                "axiom_token: yaml-axiom-token",
                "tailscale_auth_key: yaml-ts-key",
                "heartbeat_timeout_multiplier: 2.5",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    gpu_count: 1",
                "    ssh_host: host1",
                "    ssh_username: user1",
                "    worker_images:",
                "      atom-openmm:",
                "        sif_path: /shared/containers/atom-openmm.sif",
                "    nodes: 1",
                "    ntasks: 8",
                "    qos: standby",
                "    gres: gpu:1",
                "    memory_per_gpu: 60G",
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

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.database_url == "sqlite+aiosqlite:////tmp/relaymd.db"
    assert settings.log_directory == "/tmp/relaymd-logs"
    assert settings.api_token == ""
    assert settings.axiom_token == "test"
    assert settings.infisical_token == ""
    assert settings.tailscale_auth_key == ""
    assert settings.heartbeat_timeout_multiplier == 2.5
    assert settings.slurm_cluster_configs == [
        ClusterConfig(
            name="gilbreth-a30",
            partition="a30",
            account="my-account",
            ssh_host="host1",
            ssh_username="user1",
            gpu_type="a30",
            gpu_count=1,
            worker_images=_worker_images(sif_path="/shared/containers/atom-openmm.sif"),
            nodes=1,
            ntasks=8,
            qos="standby",
            gres="gpu:1",
            memory_per_gpu="60G",
            wall_time="4:00:00",
            max_pending_jobs=2,
        )
    ]


def test_missing_yaml_path_is_non_fatal(monkeypatch, tmp_path) -> None:
    missing_config_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("RELAYMD_CONFIG", str(missing_config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.database_url == "sqlite+aiosqlite:///./relaymd.db"


def test_secret_yaml_values_are_ignored(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_token: yaml-token",
                "axiom_token: yaml-axiom-token",
                "tailscale_auth_key: yaml-ts-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-token")

    settings = OrchestratorSettings()

    assert settings.api_token == ""
    assert settings.axiom_token == ""
    assert settings.tailscale_auth_key == ""


def test_storage_secret_yaml_values_are_ignored(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "b2_access_key_id: yaml-b2-access",
                "b2_secret_access_key: yaml-b2-secret",
                "cf_bearer_token: yaml-cf-token",
                "purdue_s3_access_key: yaml-purdue-access",
                "purdue_s3_secret_key: yaml-purdue-secret",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.b2_access_key_id == ""
    assert settings.b2_secret_access_key == ""
    assert settings.cf_bearer_token == ""
    assert settings.purdue_s3_access_key == ""
    assert settings.purdue_s3_secret_key == ""


def test_unregistered_env_and_yaml_alias_keys_are_ignored(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("RELAYMD_API_TOKEN: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.setenv("API_TOKEN", "env-token")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.api_token == ""


def test_infisical_token_yaml_keys_are_ignored(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "infisical_token: yaml-token",
                "INFISICAL_TOKEN: yaml-token-uppercased",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.infisical_token == ""


def test_cwd_config_overrides_home_config(monkeypatch, tmp_path) -> None:
    home_config = tmp_path / "home-config.yaml"
    home_config.write_text("database_url: sqlite+aiosqlite:////tmp/home.db\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text(
        "database_url: sqlite+aiosqlite:////tmp/cwd.db\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_DATA_ROOT", raising=False)
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(orchestrator_config, "DEFAULT_RELAYMD_CONFIG_PATH", str(home_config))
    monkeypatch.chdir(cwd_dir)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.database_url == "sqlite+aiosqlite:////tmp/cwd.db"


def test_explicit_relaymd_config_env_skips_cwd(monkeypatch, tmp_path) -> None:
    explicit_config = tmp_path / "explicit-config.yaml"
    explicit_config.write_text(
        "database_url: sqlite+aiosqlite:////tmp/explicit.db\n",
        encoding="utf-8",
    )

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text(
        "database_url: sqlite+aiosqlite:////tmp/cwd.db\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("RELAYMD_CONFIG", str(explicit_config))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.chdir(cwd_dir)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.database_url == "sqlite+aiosqlite:////tmp/explicit.db"


def test_relaymd_log_directory_env_is_loaded(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_directory: /tmp/from-yaml\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_LOG_DIRECTORY", "/tmp/from-env")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.log_directory == "/tmp/from-env"


def test_storage_provider_defaults_to_purdue(monkeypatch) -> None:
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-config-does-not-exist.yaml")
    monkeypatch.delenv("RELAYMD_STORAGE_PROVIDER", raising=False)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.storage_provider == "purdue"


def test_relaymd_storage_provider_env_override(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("storage_provider: purdue\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_STORAGE_PROVIDER", "cloudflare_backblaze")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.storage_provider == "cloudflare_backblaze"


def test_cluster_config_supports_registry_image_uri() -> None:
    cluster = ClusterConfig(
        name="test",
        partition="gpu",
        account="lab",
        ssh_host="test-host",
        ssh_username="test-user",
        worker_images=_worker_images(
            image_uri="ghcr.io/acme/relaymd-worker-atom-openmm:latest",
            sif_cache_dir=" /anvil/projects/x-bio230051/apps/relaymd/apptainer/cache ",
        ),
    )
    source = cluster.worker_image_source("atom-openmm")
    assert source.apptainer_image == "docker://ghcr.io/acme/relaymd-worker-atom-openmm:latest"
    assert source.sif_cache_dir == "/anvil/projects/x-bio230051/apps/relaymd/apptainer/cache"


def test_cluster_config_supports_gres_override() -> None:
    cluster = ClusterConfig(
        name="gilbreth-a30",
        partition="a30",
        account="my-account",
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a30",
        gpu_count=1,
        worker_images=_worker_images(sif_path="/shared/containers/atom-openmm.sif"),
        gres="gpu:1",
    )
    assert cluster.slurm_gres == "gpu:1"


def test_cluster_config_requires_worker_images() -> None:
    with pytest.raises(ValueError, match="at least one worker image source"):
        ClusterConfig(
            name="gilbreth-a30",
            partition="a30",
            account="my-account",
            ssh_host="test-host",
            ssh_username="test-user",
            gpu_type="a30",
            gpu_count=1,
        )
    with pytest.raises(ValueError, match="exactly one"):
        ClusterConfig.model_validate(
            {
                "name": "gilbreth-a30",
                "partition": "a30",
                "account": "my-account",
                "gpu_type": "a30",
                "gpu_count": 1,
                "ssh_host": "test-host",
                "ssh_username": "test-user",
                "worker_images": {
                    "atom-openmm": {
                        "sif_path": "/shared/containers/atom-openmm.sif",
                        "image_uri": "ghcr.io/acme/relaymd-worker-atom-openmm:latest",
                    }
                },
            }
        )


def test_cluster_config_rejects_multiple_memory_directives() -> None:
    with pytest.raises(ValueError, match="at most one"):
        ClusterConfig(
            name="gilbreth-a30",
            partition="a30",
            account="my-account",
            gpu_type="a30",
            gpu_count=1,
            ssh_host="test-host",
            ssh_username="test-user",
            worker_images=_worker_images(sif_path="/shared/containers/atom-openmm.sif"),
            memory="120G",
            memory_per_gpu="60G",
        )
