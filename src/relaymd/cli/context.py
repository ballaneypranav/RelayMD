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
            timeout=httpx.Timeout(self.settings.orchestrator_timeout_seconds),
            raise_on_unexpected_status=True,
        )

    def storage_client(self) -> StorageClient:
        if self.settings.storage_provider == "purdue":
            endpoint = self.settings.purdue_s3_endpoint
            bucket_name = self.settings.purdue_s3_bucket_name
            access_key_id = self.settings.purdue_s3_access_key
            secret_access_key = self.settings.purdue_s3_secret_key
        else:
            endpoint = self.settings.b2_endpoint_url
            bucket_name = self.settings.b2_bucket_name
            access_key_id = self.settings.b2_access_key_id
            secret_access_key = self.settings.b2_secret_access_key

        return StorageClient(
            storage_provider=self.settings.storage_provider,
            b2_endpoint_url=endpoint,
            b2_bucket_name=bucket_name,
            b2_access_key_id=access_key_id,
            b2_secret_access_key=secret_access_key,
            cf_worker_url=self.settings.cf_worker_url,
            cf_bearer_token=self.settings.cf_bearer_token,
            s3_region_name="us-east-1" if self.settings.storage_provider == "purdue" else None,
        )


def create_cli_context(settings: CliSettings | None = None) -> CliContext:
    return CliContext(settings=settings or load_settings())
