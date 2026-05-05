from __future__ import annotations

from typing import Any, cast

import pytest

from relaymd.orchestrator import config as orchestrator_config
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings


def test_loads_yaml_config_from_relaymd_config_path(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "database_url: sqlite+aiosqlite:////tmp/relaymd.db",
                "log_directory: /tmp/relaymd-logs",
                "api_token: yaml-token",
                "heartbeat_timeout_multiplier: 2.5",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    gpu_count: 1",
                "    ssh_host: host1",
                "    ssh_username: user1",
                "    sif_path: /shared/containers/relaymd.sif",
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
    assert settings.api_token == "yaml-token"
    assert settings.infisical_token == ""
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
            sif_path="/shared/containers/relaymd.sif",
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


def test_yaml_value_not_overridden_by_unlisted_env_var(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_token: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-token")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.api_token == "yaml-token"


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
    home_config.write_text("api_token: home-token\n", encoding="utf-8")

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "relaymd-config.yaml").write_text("api_token: cwd-token\n", encoding="utf-8")

    monkeypatch.delenv("RELAYMD_CONFIG", raising=False)
    monkeypatch.delenv("RELAYMD_DATA_ROOT", raising=False)
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(orchestrator_config, "DEFAULT_RELAYMD_CONFIG_PATH", str(home_config))
    monkeypatch.chdir(cwd_dir)

    settings = OrchestratorSettings(axiom_token="test")

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

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.api_token == "explicit-token"


def test_relaymd_log_directory_env_is_loaded(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_directory: /tmp/from-yaml\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_LOG_DIRECTORY", "/tmp/from-env")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.log_directory == "/tmp/from-env"


def test_cluster_config_supports_registry_image_uri() -> None:
    cluster = ClusterConfig(
        name="test",
        partition="gpu",
        account="lab",
        ssh_host="test-host",
        ssh_username="test-user",
        image_uri="ghcr.io/acme/relaymd-worker:latest",
    )
    assert cluster.apptainer_image == "docker://ghcr.io/acme/relaymd-worker:latest"


def test_cluster_config_supports_gres_override() -> None:
    cluster = ClusterConfig(
        name="gilbreth-a30",
        partition="a30",
        account="my-account",
        ssh_host="test-host",
        ssh_username="test-user",
        gpu_type="a30",
        gpu_count=1,
        sif_path="/shared/containers/relaymd.sif",
        gres="gpu:1",
    )
    assert cluster.slurm_gres == "gpu:1"


def test_cluster_config_requires_exactly_one_image_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
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
        ClusterConfig(
            name="gilbreth-a30",
            partition="a30",
            account="my-account",
            gpu_type="a30",
            gpu_count=1,
            ssh_host="test-host",
            ssh_username="test-user",
            sif_path="/shared/containers/relaymd.sif",
            image_uri="ghcr.io/acme/relaymd-worker:latest",
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
            sif_path="/shared/containers/relaymd.sif",
            memory="120G",
            memory_per_gpu="60G",
        )


def test_load_settings_hydrates_api_credentials_from_infisical(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_token: yaml-token",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    ssh_host: test-host",
                "    ssh_username: test-user",
                "    gpu_count: 1",
                "    sif_path: /shared/containers/relaymd.sif",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("AXIOM_TOKEN", raising=False)
    monkeypatch.delenv("TAILSCALE_AUTH_KEY", raising=False)

    values = {
        "RELAYMD_API_TOKEN": "relaymd-token",
        "AXIOM_TOKEN": "axiom-test-token",
        "TAILSCALE_AUTH_KEY": "tskey-auth-test",
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
            return _FakeSecret(values[options.secret_name])

    monkeypatch.setattr(
        orchestrator_config,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = orchestrator_config.load_settings()

    assert settings.api_token == "relaymd-token"
    assert settings.axiom_token == "axiom-test-token"
    assert settings.tailscale_auth_key == "tskey-auth-test"
    assert secret_calls == [
        "RELAYMD_API_TOKEN",
        "AXIOM_TOKEN",
        "TAILSCALE_AUTH_KEY",
    ]


def test_load_settings_uses_infisical_even_when_yaml_secrets_exist(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_token: yaml-token",
                "axiom_token: yaml-axiom-token",
                "tailscale_auth_key: tskey-sif-test",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    ssh_host: test-host",
                "    ssh_username: test-user",
                "    gpu_count: 1",
                "    sif_path: /shared/containers/relaymd.sif",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    values = {
        "RELAYMD_API_TOKEN": "relaymd-token",
        "AXIOM_TOKEN": "axiom-token",
        "TAILSCALE_AUTH_KEY": "tskey-infisical",
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
        orchestrator_config,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = orchestrator_config.load_settings()

    assert settings.api_token == "relaymd-token"
    assert settings.axiom_token == "axiom-token"
    assert settings.tailscale_auth_key == "tskey-infisical"


def test_load_settings_does_not_fetch_ghcr_credentials_from_infisical(
    monkeypatch, tmp_path
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_token: yaml-token",
                "slurm_cluster_configs:",
                "  - name: non-ghcr-cluster",
                "    partition: gpu",
                "    account: my-account",
                "    gpu_type: a30",
                "    ssh_host: test-host",
                "    ssh_username: test-user",
                "    gpu_count: 1",
                "    image_uri: docker.io/library/ubuntu:latest",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    values = {
        "RELAYMD_API_TOKEN": "relaymd-token",
        "AXIOM_TOKEN": "axiom-token",
        "TAILSCALE_AUTH_KEY": "tskey-infisical",
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
            return _FakeSecret(values[options.secret_name])

    monkeypatch.setattr(
        orchestrator_config,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = orchestrator_config.load_settings()

    assert settings.api_token == "relaymd-token"
    assert settings.axiom_token == "axiom-token"
    assert settings.tailscale_auth_key == "tskey-infisical"
    assert "GHCR_USERNAME" not in secret_calls
    assert "GHCR_PAT" not in secret_calls


def test_slurm_cluster_partition_must_be_singular_string() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-a30",
                    "partition": "a30",
                    "account": "my-account",
                    "ssh_host": "host1",
                    "ssh_username": "user1",
                    "sif_path": "/shared/containers/relaymd.sif",
                }
            ],
        ),
    )

    assert settings.slurm_cluster_configs[0].partition == "a30"


def test_slurm_cluster_partition_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid partition list"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "gilbreth",
                        "partition": ["a30", "a100"],
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    }
                ],
            ),
        )


def test_slurm_cluster_inheritance_child_overrides_parent() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "partition": "a30",
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "qos": "standby",
                    "sif_path": "/shared/containers/base.sif",
                },
                {
                    "name": "gilbreth-a100",
                    "extends": "gilbreth-template",
                    "partition": "a100-80gb",
                    "account": "override-account",
                    "ssh_host": "override-host",
                },
            ],
        ),
    )

    assert settings.slurm_cluster_configs == [
        ClusterConfig(
            name="gilbreth-a100",
            extends="gilbreth-template",
            is_template=False,
            partition="a100-80gb",
            account="override-account",
            ssh_host="override-host",
            ssh_username="base-user",
            qos="standby",
            sif_path="/shared/containers/base.sif",
        )
    ]


def test_slurm_cluster_templates_are_excluded_from_runtime_clusters() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "partition": "a30",
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "sif_path": "/shared/containers/base.sif",
                },
                {
                    "name": "gilbreth-a30",
                    "extends": "gilbreth-template",
                    "partition": "a30",
                },
            ],
        ),
    )

    assert [cluster.name for cluster in settings.slurm_cluster_configs] == ["gilbreth-a30"]


def test_slurm_cluster_intermediate_templates_are_excluded_from_runtime_clusters() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "sif_path": "/shared/containers/base.sif",
                },
                {
                    "name": "gilbreth-standby-template",
                    "is_template": True,
                    "extends": "gilbreth-template",
                    "qos": "standby",
                },
                {
                    "name": "gilbreth-standby-a30",
                    "extends": "gilbreth-standby-template",
                    "partition": "a30",
                },
            ],
        ),
    )

    assert [cluster.name for cluster in settings.slurm_cluster_configs] == ["gilbreth-standby-a30"]
    assert settings.slurm_cluster_configs[0].qos == "standby"


def test_slurm_cluster_inheritance_unknown_parent_fails_fast() -> None:
    with pytest.raises(ValueError, match="extends unknown cluster"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "gilbreth-a30",
                        "extends": "missing-template",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    }
                ],
            ),
        )


def test_slurm_cluster_inheritance_cycle_fails_fast() -> None:
    with pytest.raises(ValueError, match="cycle detected"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "cluster-a",
                        "extends": "cluster-b",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    },
                    {
                        "name": "cluster-b",
                        "extends": "cluster-a",
                        "partition": "a100",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    },
                ],
            ),
        )


def test_slurm_cluster_duplicate_names_fail_fast() -> None:
    with pytest.raises(ValueError, match="duplicate slurm cluster config name"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "cluster-a",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    },
                    {
                        "name": "cluster-a",
                        "partition": "a100",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "sif_path": "/shared/containers/relaymd.sif",
                    },
                ],
            ),
        )
