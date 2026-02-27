from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
import respx
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from httpx import HTTPStatusError, Response
from moto import mock_aws
from relaymd.storage import StorageClient


def _disable_retry_sleep(monkeypatch) -> None:
    monkeypatch.setattr("tenacity.nap.sleep", lambda _seconds: None)


def _build_client() -> StorageClient:
    return StorageClient(
        b2_endpoint_url="https://s3.us-east-1.amazonaws.com",
        b2_bucket_name="relaymd-bucket",
        b2_access_key_id="test-access-key-id",
        b2_secret_access_key="test-secret-access-key",
        cf_worker_url="https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev",
        cf_bearer_token="download-token",
    )


def test_upload_file_and_list_keys_use_s3_not_cloudflare(tmp_path: Path) -> None:
    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"payload")

    with mock_aws():
        client = _build_client()
        client._s3.create_bucket(Bucket="relaymd-bucket")

        with respx.mock(assert_all_called=False) as router:
            cf_route = router.route(
                host="cloudflare-backblaze-worker.pranav-purdue-account.workers.dev"
            ).mock(return_value=Response(500))

            client.upload_file(local_path=local_path, b2_key="jobs/1/input/payload.bin")
            keys = client.list_keys(prefix="jobs/1/")

            assert keys == ["jobs/1/input/payload.bin"]
            assert not cf_route.called
            assert client._s3.meta.endpoint_url == "https://s3.us-east-1.amazonaws.com"


def test_download_file_uses_cloudflare_worker_with_bearer_token(tmp_path: Path) -> None:
    client = _build_client()
    destination = tmp_path / "downloads" / "checkpoint.chk"
    key = "jobs/abc/checkpoints/latest"
    expected_url = (
        "https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev/files/"
        "jobs/abc/checkpoints/latest"
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.get(expected_url).mock(
            return_value=Response(200, content=b"checkpoint-bytes")
        )

        client.download_file(b2_key=key, local_path=destination)

    assert destination.read_bytes() == b"checkpoint-bytes"
    assert route.called
    assert route.calls.last.request.headers["Authorization"] == "Bearer download-token"


def test_upload_file_retries_on_transient_s3_error_then_succeeds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"payload")
    client = _build_client()
    attempts = {"count": 0}

    def flaky_upload(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ClientError(
                error_response={"Error": {"Code": "SlowDown", "Message": "try again"}},
                operation_name="PutObject",
            )
        return None

    _disable_retry_sleep(monkeypatch)
    upload_mock = Mock(side_effect=flaky_upload)
    monkeypatch.setattr(cast(Any, client._s3), "upload_file", upload_mock)

    client.upload_file(local_path=local_path, b2_key="jobs/1/input/payload.bin")

    assert attempts["count"] == 3


def test_upload_file_raises_after_five_attempts(tmp_path: Path, monkeypatch) -> None:
    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"payload")
    client = _build_client()
    error = ClientError(
        error_response={"Error": {"Code": "RequestTimeout", "Message": "timeout"}},
        operation_name="PutObject",
    )

    _disable_retry_sleep(monkeypatch)
    upload_mock = Mock(side_effect=error)
    monkeypatch.setattr(cast(Any, client._s3), "upload_file", upload_mock)

    with pytest.raises(ClientError):
        client.upload_file(local_path=local_path, b2_key="jobs/1/input/payload.bin")

    assert upload_mock.call_count == 5


def test_upload_file_access_denied_does_not_retry(tmp_path: Path, monkeypatch) -> None:
    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"payload")
    client = _build_client()
    error = ClientError(
        error_response={
            "Error": {"Code": "AccessDenied", "Message": "denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        operation_name="PutObject",
    )

    _disable_retry_sleep(monkeypatch)
    upload_mock = Mock(side_effect=error)
    monkeypatch.setattr(cast(Any, client._s3), "upload_file", upload_mock)

    with pytest.raises(ClientError):
        client.upload_file(local_path=local_path, b2_key="jobs/1/input/payload.bin")

    assert upload_mock.call_count == 1


def test_download_file_404_does_not_retry(tmp_path: Path, monkeypatch) -> None:
    client = _build_client()
    destination = tmp_path / "downloads" / "missing.chk"
    key = "jobs/abc/checkpoints/missing"
    expected_url = (
        "https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev/files/"
        "jobs/abc/checkpoints/missing"
    )

    _disable_retry_sleep(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        route = router.get(expected_url).mock(return_value=Response(404, text="not found"))
        with pytest.raises(HTTPStatusError):
            client.download_file(b2_key=key, local_path=destination)

    assert len(route.calls) == 1


def test_upload_file_passes_transfer_config(tmp_path: Path) -> None:
    local_path = tmp_path / "tiny.bin"
    local_path.write_bytes(b"x")

    with mock_aws():
        client = _build_client()
        client._s3.create_bucket(Bucket="relaymd-bucket")

        with patch.object(client._s3, "upload_file", wraps=client._s3.upload_file) as upload_spy:
            client.upload_file(local_path=local_path, b2_key="jobs/1/input/tiny.bin")

        _, kwargs = upload_spy.call_args
        assert "Config" in kwargs
        assert isinstance(kwargs["Config"], TransferConfig)


def test_list_keys_paginates_beyond_1000_results() -> None:
    prefix = "jobs/huge/checkpoints/"
    object_count = 1005

    with mock_aws():
        client = _build_client()
        client._s3.create_bucket(Bucket="relaymd-bucket")

        for index in range(object_count):
            key = f"{prefix}{index:04d}.chk"
            client._s3.put_object(Bucket="relaymd-bucket", Key=key, Body=b"x")

        keys = client.list_keys(prefix=prefix)

    assert len(keys) == object_count
    assert keys[0] == f"{prefix}0000.chk"
    assert keys[-1] == f"{prefix}1004.chk"


def test_storage_client_normalizes_host_only_urls(monkeypatch) -> None:
    boto_client = Mock()
    monkeypatch.setattr("relaymd.storage.client.boto3.client", boto_client)

    client = StorageClient(
        b2_endpoint_url="s3.us-east-005.backblazeb2.com",
        b2_bucket_name="relaymd-bucket",
        b2_access_key_id="test-access-key-id",
        b2_secret_access_key="test-secret-access-key",
        cf_worker_url="cloudflare-backblaze-worker.pranav-purdue-account.workers.dev",
        cf_bearer_token="download-token",
    )

    assert client._cf_worker_url == "https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev"
    _, kwargs = boto_client.call_args
    assert kwargs["endpoint_url"] == "https://s3.us-east-005.backblazeb2.com"
