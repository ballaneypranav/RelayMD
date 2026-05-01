from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from relaymd_api_client.errors import UnexpectedStatus
from relaymd_api_client.models.http_validation_error import HTTPValidationError
from relaymd_api_client.models.job_conflict import JobConflict
from relaymd_api_client.models.job_read import JobRead
from relaymd_api_client.models.worker_read import WorkerRead

from relaymd.cli.config import CliSettings
from relaymd.cli.context import CliContext
from relaymd.cli.services.jobs_service import JobsService
from relaymd.cli.services.submit_service import SubmitService
from relaymd.cli.services.workers_service import WorkersService


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
            "latest_checkpoint_path": None,
            "last_checkpoint_at": None,
            "assigned_worker_id": None,
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


def test_jobs_service_list_jobs_returns_typed_payload(monkeypatch) -> None:
    context = _FakeContext()
    expected = [_make_job_read()]
    sync = Mock(return_value=expected)
    monkeypatch.setattr("relaymd.cli.services.jobs_service.list_jobs_jobs_get.sync", sync)

    jobs = JobsService(_as_cli_context(context)).list_jobs()

    assert jobs == expected
    sync.assert_called_once_with(client=context.client, x_api_token="test-token")


@pytest.mark.parametrize("payload", [None, "not-a-list"])
def test_jobs_service_list_jobs_rejects_non_list(monkeypatch, payload: object) -> None:
    context = _FakeContext()
    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.list_jobs_jobs_get.sync",
        Mock(return_value=payload),
    )

    with pytest.raises(RuntimeError, match="Failed to parse list jobs response"):
        JobsService(_as_cli_context(context)).list_jobs()


def test_jobs_service_list_jobs_rejects_unexpected_item_type(monkeypatch) -> None:
    context = _FakeContext()
    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.list_jobs_jobs_get.sync",
        Mock(return_value=[object()]),
    )

    with pytest.raises(RuntimeError, match="Unexpected response model"):
        JobsService(_as_cli_context(context)).list_jobs()


def test_jobs_service_get_job_rejects_non_job_model(monkeypatch) -> None:
    context = _FakeContext()
    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.get_job_jobs_job_id_get.sync",
        Mock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="Failed to parse get job response"):
        JobsService(_as_cli_context(context)).get_job(job_id=uuid4())


@pytest.mark.parametrize(
    "response",
    [
        HTTPValidationError.from_dict({"detail": []}),
        JobConflict(message="conflict"),
    ],
)
def test_jobs_service_cancel_job_surfaces_typed_errors(monkeypatch, response: object) -> None:
    context = _FakeContext()
    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.cancel_job_jobs_job_id_delete.sync",
        Mock(return_value=response),
    )

    with pytest.raises(RuntimeError):
        JobsService(_as_cli_context(context)).cancel_job(job_id=uuid4(), force=True)


def test_jobs_service_requeue_job_handles_success_and_errors(monkeypatch) -> None:
    context = _FakeContext()
    service = JobsService(_as_cli_context(context))

    success = _make_job_read()
    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.requeue_job_jobs_job_id_requeue_post.sync",
        Mock(return_value=success),
    )
    assert service.requeue_job(job_id=uuid4()) == success

    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.requeue_job_jobs_job_id_requeue_post.sync",
        Mock(return_value=JobConflict(message="conflict")),
    )
    with pytest.raises(RuntimeError):
        service.requeue_job(job_id=uuid4())

    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.requeue_job_jobs_job_id_requeue_post.sync",
        Mock(return_value=HTTPValidationError.from_dict({"detail": []})),
    )
    with pytest.raises(RuntimeError):
        service.requeue_job(job_id=uuid4())

    monkeypatch.setattr(
        "relaymd.cli.services.jobs_service.requeue_job_jobs_job_id_requeue_post.sync",
        Mock(return_value=None),
    )
    with pytest.raises(RuntimeError, match="Failed to parse requeue response"):
        service.requeue_job(job_id=uuid4())


def test_submit_service_upload_bundle_delegates_to_storage() -> None:
    context = _FakeContext()
    archive = Path("/tmp/bundle.tar.gz")

    SubmitService(_as_cli_context(context)).upload_bundle(
        local_archive=archive,
        b2_key="jobs/a/input/bundle.tar.gz",
    )

    context.storage.upload_file.assert_called_once_with(archive, "jobs/a/input/bundle.tar.gz")


def test_submit_service_upload_bundle_requires_b2_settings() -> None:
    context = _FakeContext()
    context.settings = CliSettings(api_token="test-token")

    with pytest.raises(RuntimeError, match="Missing required B2 storage settings for submit"):
        SubmitService(_as_cli_context(context)).upload_bundle(
            local_archive=Path("/tmp/bundle.tar.gz"),
            b2_key="jobs/a/input/bundle.tar.gz",
        )

    context.storage.upload_file.assert_not_called()


def test_submit_service_register_job_rejects_non_job_model(monkeypatch) -> None:
    context = _FakeContext()
    monkeypatch.setattr(
        "relaymd.cli.services.submit_service.create_job_jobs_post.sync",
        Mock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="Failed to parse create job response"):
        SubmitService(_as_cli_context(context)).register_job(
            job_id=str(uuid4()),
            title="train",
            b2_key="jobs/a/input/bundle.tar.gz",
        )


def test_submit_service_register_job_surfaces_helpful_404_hint(monkeypatch) -> None:
    context = _FakeContext()
    context.settings = CliSettings(
        api_token="test-token",
        orchestrator_url="http://127.0.0.1:36158",
        b2_endpoint_url="https://b2.example",
        b2_bucket_name="relaymd-bucket",
        b2_access_key_id="access",
        b2_secret_access_key="secret",
    )
    monkeypatch.setattr(
        "relaymd.cli.services.submit_service.create_job_jobs_post.sync",
        Mock(side_effect=UnexpectedStatus(404, b'{"detail":"Not Found"}')),
    )

    with pytest.raises(RuntimeError, match="POST /jobs returned 404 from http://127.0.0.1:36158"):
        SubmitService(_as_cli_context(context)).register_job(
            job_id=str(uuid4()),
            title="train",
            b2_key="jobs/a/input/bundle.tar.gz",
        )


def test_workers_service_list_workers_validates_shape(monkeypatch) -> None:
    context = _FakeContext()
    service = WorkersService(_as_cli_context(context))

    expected = [_make_worker_read()]
    monkeypatch.setattr(
        "relaymd.cli.services.workers_service.list_workers_workers_get.sync",
        Mock(return_value=expected),
    )
    assert service.list_workers() == expected

    monkeypatch.setattr(
        "relaymd.cli.services.workers_service.list_workers_workers_get.sync",
        Mock(return_value=None),
    )
    with pytest.raises(RuntimeError, match="Failed to parse list workers response"):
        service.list_workers()

    monkeypatch.setattr(
        "relaymd.cli.services.workers_service.list_workers_workers_get.sync",
        Mock(return_value=[object()]),
    )
    with pytest.raises(RuntimeError, match="Unexpected response model"):
        service.list_workers()
