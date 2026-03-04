from __future__ import annotations

import pytest

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
    monkeypatch.delenv("RELAYMD_INFISICAL_TOKEN", raising=False)

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.database_url == "sqlite+aiosqlite:////tmp/relaymd.db"
    assert settings.api_token == "yaml-token"
    assert settings.infisical_token == "yaml-infisical"
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


def test_env_secret_overrides_yaml_value(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_token: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-token")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.api_token == "yaml-token"


def test_env_secret_overrides_yaml_alias_key(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("RELAYMD_API_TOKEN: yaml-token\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.setenv("API_TOKEN", "env-token")

    settings = OrchestratorSettings(axiom_token="test")

    assert settings.api_token == ""


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


def test_load_settings_hydrates_registry_credentials_from_infisical(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "api_token: yaml-token",
                "infisical_token: client-id:client-secret",
                "slurm_cluster_configs:",
                "  - name: gilbreth-a30",
                "    partition: a30",
                "    account: my-account",
                "    gpu_type: a30",
                "    ssh_host: test-host",
                "    ssh_username: test-user",
                "    gpu_count: 1",
                "    image_uri: ghcr.io/acme/relaymd-worker:latest",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_CONFIG", str(config_path))
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("AXIOM_TOKEN", raising=False)
    monkeypatch.delenv("RELAYMD_AXIOM_TOKEN", raising=False)
    monkeypatch.delenv("TAILSCALE_AUTH_KEY", raising=False)
    monkeypatch.delenv("APPTAINER_DOCKER_USERNAME", raising=False)
    monkeypatch.delenv("SINGULARITY_DOCKER_USERNAME", raising=False)
    monkeypatch.delenv("GHCR_USERNAME", raising=False)
    monkeypatch.delenv("APPTAINER_DOCKER_PASSWORD", raising=False)
    monkeypatch.delenv("SINGULARITY_DOCKER_PASSWORD", raising=False)
    monkeypatch.delenv("GHCR_PAT", raising=False)
    monkeypatch.delenv("GHCR_TOKEN", raising=False)

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
    assert settings.apptainer_docker_username == ""
    assert settings.apptainer_docker_password == ""
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
                "infisical_token: client-id:client-secret",
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
    assert settings.apptainer_docker_username == ""
    assert settings.apptainer_docker_password == ""
