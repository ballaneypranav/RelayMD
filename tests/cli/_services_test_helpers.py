from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

from relaymd_api_client.models.job_read import JobRead
from relaymd_api_client.models.worker_read import WorkerRead

from relaymd.cli.config import CliSettings
from relaymd.cli.context import CliContext


class _ClientContextManager:
    def __init__(self, client: object) -> None:
        self._client = client

    def __enter__(self) -> object:
        return self._client

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False


class _FakeContext:
    def __init__(self) -> None:
        self.settings = CliSettings(
            storage_provider="cloudflare_backblaze",
            api_token="test-token",
            b2_endpoint_url="https://b2.example",
            b2_bucket_name="relaymd-bucket",
            b2_access_key_id="access",
            b2_secret_access_key="secret",
        )
        self.client = object()
        self.storage = Mock()

    def api_client(self) -> _ClientContextManager:
        return _ClientContextManager(self.client)

    def storage_client(self) -> Mock:
        return self.storage


def _as_cli_context(context: _FakeContext) -> CliContext:
    return cast(CliContext, context)


def _make_job_read() -> JobRead:
    now = datetime.now(UTC).isoformat()
    return JobRead.from_dict(
        {
            "id": str(uuid4()),
            "title": "job-a",
            "status": "queued",
            "input_bundle_path": "jobs/a/input/bundle.tar.gz",
            "assigned_at": None,
            "started_at": None,
            "status_changed_at": now,
            "latest_checkpoint_manifest_path": None,
            "latest_checkpoint_path": None,
            "last_checkpoint_at": None,
            "assigned_worker_id": None,
            "created_at": now,
            "updated_at": now,
        }
    )


def _make_checkpoint_job_read() -> JobRead:
    now = datetime.now(UTC).isoformat()
    return JobRead.from_dict(
        {
            "id": str(uuid4()),
            "title": "job-checkpoint",
            "status": "running",
            "input_bundle_path": "jobs/a/input/bundle.tar.gz",
            "assigned_at": now,
            "started_at": now,
            "status_changed_at": now,
            "latest_checkpoint_manifest_path": "jobs/abc/checkpoints/manifest.json",
            "latest_checkpoint_path": "jobs/abc/checkpoints/manifest.json",
            "last_checkpoint_at": now,
            "assigned_worker_id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
        }
    )


def _make_worker_read() -> WorkerRead:
    now = datetime.now(UTC).isoformat()
    return WorkerRead.from_dict(
        {
            "id": str(uuid4()),
            "platform": "hpc",
            "gpu_model": "NVIDIA A100",
            "gpu_count": 1,
            "vram_gb": 80,
            "status": "active",
            "last_heartbeat": now,
            "registered_at": now,
        }
    )
