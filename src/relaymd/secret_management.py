from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

DependencyLoader = Callable[[], tuple[type[Any], type[Any], type[Any]]]


class MissingRequiredSecretsError(RuntimeError):
    def __init__(self, missing_secret_names: list[str]) -> None:
        self.missing_secret_names = sorted(set(missing_secret_names))
        missing = ", ".join(self.missing_secret_names)
        super().__init__(f"Missing required Infisical secrets: {missing}")


class InfisicalSecretManager:
    def __init__(
        self,
        *,
        machine_token: str,
        dependency_loader: DependencyLoader,
        base_url: str,
        workspace_id: str,
        environment: str,
        secret_path: str,
    ) -> None:
        self._client_id, self._client_secret = self.parse_machine_token(machine_token)
        self._dependency_loader = dependency_loader
        self._base_url = base_url
        self._workspace_id = workspace_id
        self._environment = environment
        self._secret_path = secret_path

    @staticmethod
    def parse_machine_token(raw_token: str) -> tuple[str, str]:
        if ":" not in raw_token:
            raise RuntimeError(
                "INFISICAL_TOKEN is malformed; expected format <client_id>:<client_secret>"
            )

        client_id, client_secret = raw_token.split(":", 1)
        if not client_id or not client_secret:
            raise RuntimeError(
                "INFISICAL_TOKEN is malformed; expected non-empty <client_id>:<client_secret>"
            )
        return client_id, client_secret

    def _build_client(self) -> tuple[Any, type[Any]]:
        ClientSettings, InfisicalClient, GetSecretOptions = self._dependency_loader()
        client = InfisicalClient(
            settings=ClientSettings(
                client_id=self._client_id,
                client_secret=self._client_secret,
                site_url=self._base_url,
            )
        )
        return client, GetSecretOptions

    def _get_secret(self, client: Any, get_secret_options: type[Any], name: str) -> str:
        return client.getSecret(
            get_secret_options(
                secret_name=name,
                project_id=self._workspace_id,
                environment=self._environment,
                path=self._secret_path,
            )
        ).secret_value

    @staticmethod
    def _is_secret_not_found_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "not found" in message
            or "no secret found" in message
            or "does not exist" in message
            or "unable to find" in message
        )

    def fetch_mapped_secrets(
        self,
        *,
        required: Mapping[str, str],
        optional: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        optional = optional or {}
        client, get_secret_options = self._build_client()
        resolved: dict[str, str] = {}
        missing_required_secret_names: list[str] = []

        for field_name, secret_name in required.items():
            try:
                resolved[field_name] = self._get_secret(client, get_secret_options, secret_name)
            except Exception as exc:  # noqa: BLE001
                if not self._is_secret_not_found_error(exc):
                    raise
                missing_required_secret_names.append(secret_name)

        if missing_required_secret_names:
            raise MissingRequiredSecretsError(missing_required_secret_names)

        for field_name, secret_name in optional.items():
            try:
                resolved[field_name] = self._get_secret(client, get_secret_options, secret_name)
            except Exception as exc:  # noqa: BLE001
                if not self._is_secret_not_found_error(exc):
                    raise
                continue

        return resolved


class OrchestratorSecretManager(InfisicalSecretManager):
    def fetch_settings_values(
        self, *, include_tailscale_auth_key: bool, include_registry_credentials: bool
    ) -> dict[str, str]:
        required: dict[str, str] = {
            "api_token": "RELAYMD_API_TOKEN",
            "axiom_token": "AXIOM_TOKEN",
        }
        if include_registry_credentials:
            required["apptainer_docker_username"] = "GHCR_USERNAME"
            required["apptainer_docker_password"] = "GHCR_PAT"
        if include_tailscale_auth_key:
            required["tailscale_auth_key"] = "TAILSCALE_AUTH_KEY"
        return self.fetch_mapped_secrets(required=required)


class CliSecretManager(InfisicalSecretManager):
    def fetch_settings_values(self) -> dict[str, str]:
        return self.fetch_mapped_secrets(
            required={
                "api_token": "RELAYMD_API_TOKEN",
                "b2_endpoint_url": "B2_ENDPOINT",
                "b2_bucket_name": "BUCKET_NAME",
                "b2_access_key_id": "B2_APPLICATION_KEY_ID",
                "b2_secret_access_key": "B2_APPLICATION_KEY",
            },
            optional={
                "cf_bearer_token": "DOWNLOAD_BEARER_TOKEN",
            },
        )


class WorkerSecretManager(InfisicalSecretManager):
    def fetch_bootstrap_values(self) -> dict[str, str]:
        return self.fetch_mapped_secrets(
            required={
                "axiom_token": "AXIOM_TOKEN",
                "b2_application_key_id": "B2_APPLICATION_KEY_ID",
                "b2_application_key": "B2_APPLICATION_KEY",
                "b2_endpoint": "B2_ENDPOINT",
                "bucket_name": "BUCKET_NAME",
                "tailscale_auth_key": "TAILSCALE_AUTH_KEY",
                "relaymd_api_token": "RELAYMD_API_TOKEN",
                "relaymd_orchestrator_url": "RELAYMD_ORCHESTRATOR_URL",
            },
            optional={
                "download_bearer_token": "DOWNLOAD_BEARER_TOKEN",
            },
        )
