from __future__ import annotations

from relaymd.orchestrator import config as orchestrator_config


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
                "    worker_images:",
                "      atom-openmm:",
                "        sif_path: /shared/containers/atom-openmm.sif",
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
                "    worker_images:",
                "      atom-openmm:",
                "        sif_path: /shared/containers/atom-openmm.sif",
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
                "    worker_images:",
                "      atom-openmm:",
                "        image_uri: docker.io/library/ubuntu:latest",
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
