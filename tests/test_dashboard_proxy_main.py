from __future__ import annotations

import pytest

from relaymd import dashboard_proxy_main


def test_load_proxy_settings_hydrates_from_infisical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("RELAYMD_PROXY_UPSTREAM_URL", "http://orchestrator.local:36158")

    values = {
        "RELAYMD_API_TOKEN": "api-token",
        "RELAYMD_DASHBOARD_USERNAME": "operator",
        "RELAYMD_DASHBOARD_PASSWORD": "password",
        "RELAYMD_DASHBOARD_SESSION_SECRET": "session-secret",
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
        def __init__(self, settings: _FakeClientSettings) -> None:
            self.settings = settings

        def getSecret(self, options: _FakeGetSecretOptions) -> _FakeSecret:
            return _FakeSecret(values[options.secret_name])

    monkeypatch.setattr(
        dashboard_proxy_main,
        "_get_infisical_client_dependencies",
        lambda: (_FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions),
    )

    settings = dashboard_proxy_main.load_proxy_settings()

    assert settings.upstream_url == "http://orchestrator.local:36158"
    assert settings.upstream_api_token == "api-token"
    assert settings.username == "operator"
    assert settings.password == "password"
    assert settings.session_secret == "session-secret"


def test_load_proxy_settings_requires_infisical_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is required"):
        dashboard_proxy_main.load_proxy_settings()
