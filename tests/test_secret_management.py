from __future__ import annotations

import pytest

from relaymd.secret_management import InfisicalSecretManager, MissingRequiredSecretsError


def _dependency_loader_for(
    *,
    values: dict[str, str],
    errors: dict[str, Exception] | None = None,
):
    errors = errors or {}

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
            _ = (project_id, environment, path)
            self.secret_name = secret_name

    class _FakeSecret:
        def __init__(self, secret_value: str) -> None:
            self.secret_value = secret_value

    class _FakeInfisicalClient:
        def __init__(self, settings: _FakeClientSettings) -> None:
            self.settings = settings

        def getSecret(self, options: _FakeGetSecretOptions) -> _FakeSecret:
            secret_name = options.secret_name
            if secret_name in errors:
                raise errors[secret_name]
            return _FakeSecret(values[secret_name])

    return _FakeClientSettings, _FakeInfisicalClient, _FakeGetSecretOptions


def _build_manager(
    *,
    values: dict[str, str],
    errors: dict[str, Exception] | None = None,
) -> InfisicalSecretManager:
    return InfisicalSecretManager(
        machine_token="client-id:client-secret",
        dependency_loader=lambda: _dependency_loader_for(values=values, errors=errors),
        base_url="https://app.infisical.com",
        workspace_id="workspace",
        environment="prod",
        secret_path="/RelayMD",
    )


def test_fetch_mapped_secrets_marks_only_not_found_as_missing_required() -> None:
    manager = _build_manager(
        values={"PRESENT": "ok"},
        errors={"MISSING": Exception("Secret not found")},
    )

    with pytest.raises(MissingRequiredSecretsError) as exc_info:
        manager.fetch_mapped_secrets(required={"present": "PRESENT", "missing": "MISSING"})

    assert exc_info.value.missing_secret_names == ["MISSING"]


def test_fetch_mapped_secrets_reraises_required_provider_failures() -> None:
    manager = _build_manager(
        values={"PRESENT": "ok"},
        errors={"MISSING": Exception("Infisical request failed: unauthorized")},
    )

    with pytest.raises(Exception, match="unauthorized"):
        manager.fetch_mapped_secrets(required={"present": "PRESENT", "missing": "MISSING"})


def test_fetch_mapped_secrets_ignores_optional_not_found() -> None:
    manager = _build_manager(
        values={"REQUIRED": "value"},
        errors={"OPTIONAL": Exception("Secret does not exist")},
    )

    resolved = manager.fetch_mapped_secrets(
        required={"required": "REQUIRED"},
        optional={"optional": "OPTIONAL"},
    )

    assert resolved == {"required": "value"}


def test_fetch_mapped_secrets_reraises_optional_provider_failures() -> None:
    manager = _build_manager(
        values={"REQUIRED": "value"},
        errors={"OPTIONAL": Exception("request timeout contacting Infisical")},
    )

    with pytest.raises(Exception, match="timeout"):
        manager.fetch_mapped_secrets(
            required={"required": "REQUIRED"},
            optional={"optional": "OPTIONAL"},
        )


def test_fetch_mapped_secrets_reraises_optional_keyerror() -> None:
    manager = _build_manager(
        values={"REQUIRED": "value"},
        errors={"OPTIONAL": KeyError("DOWNLOAD_BEARER_TOKEN")},
    )

    with pytest.raises(KeyError):
        manager.fetch_mapped_secrets(
            required={"required": "REQUIRED"},
            optional={"optional": "OPTIONAL"},
        )
