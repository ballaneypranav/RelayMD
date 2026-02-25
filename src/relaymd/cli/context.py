from __future__ import annotations

from dataclasses import dataclass

import httpx
from relaymd_api_client.client import Client as RelaymdApiClient

from relaymd.cli.config import CliSettings, load_settings
from relaymd.storage import StorageClient


@dataclass(frozen=True)
class CliContext:
    settings: CliSettings

    def api_client(self) -> RelaymdApiClient:
        return RelaymdApiClient(
            base_url=self.settings.orchestrator_url.rstrip("/"),
            timeout=httpx.Timeout(30.0),
            raise_on_unexpected_status=True,
        )

    def storage_client(self) -> StorageClient:
        return StorageClient(
            b2_endpoint_url=self.settings.b2_endpoint_url,
            b2_bucket_name=self.settings.b2_bucket_name,
            b2_access_key_id=self.settings.b2_access_key_id,
            b2_secret_access_key=self.settings.b2_secret_access_key,
            cf_worker_url=self.settings.cf_worker_url,
            cf_bearer_token=self.settings.cf_bearer_token,
        )


def create_cli_context(settings: CliSettings | None = None) -> CliContext:
    return CliContext(settings=settings or load_settings())
