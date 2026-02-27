from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import boto3
import httpx
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import BotoCoreError, ClientError, EndpointResolutionError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _normalize_url(url: str) -> str:
    normalized = url.strip()
    if "://" not in normalized:
        normalized = f"https://{normalized}"
    return normalized


def _is_retryable_http_error(exception: BaseException) -> bool:
    if not isinstance(exception, httpx.HTTPError):
        return False
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        if 400 <= status_code < 500:
            return False
    return True


def _is_retryable_s3_error(exception: BaseException) -> bool:
    if isinstance(exception, (EndpointResolutionError, BotoCoreError)):
        return True
    if not isinstance(exception, ClientError):
        return False

    error = exception.response.get("Error", {})
    code = str(error.get("Code", ""))
    if code in {"AccessDenied", "InvalidBucketName", "NoSuchBucket", "NoSuchKey"}:
        return False

    response_metadata = exception.response.get("ResponseMetadata", {})
    status_code = response_metadata.get("HTTPStatusCode")
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return code in {"RequestTimeout", "SlowDown", "Throttling", "ThrottlingException"}

    return True


class StorageClient:
    def __init__(
        self,
        b2_endpoint_url: str,
        b2_bucket_name: str,
        b2_access_key_id: str,
        b2_secret_access_key: str,
        cf_worker_url: str,
        cf_bearer_token: str,
    ) -> None:
        self._b2_bucket_name = b2_bucket_name
        self._cf_worker_url = _normalize_url(cf_worker_url).rstrip("/")
        self._cf_bearer_token = cf_bearer_token
        self._transfer_config = TransferConfig(
            multipart_threshold=16 * 1024 * 1024,
            multipart_chunksize=16 * 1024 * 1024,
            max_concurrency=4,
            use_threads=True,
        )
        normalized_b2_endpoint_url = _normalize_url(b2_endpoint_url)
        self._s3 = boto3.client(
            "s3",
            endpoint_url=normalized_b2_endpoint_url,
            aws_access_key_id=b2_access_key_id,
            aws_secret_access_key=b2_secret_access_key,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable_s3_error),
        reraise=True,
    )
    def upload_file(self, local_path: Path, b2_key: str) -> None:
        self._s3.upload_file(
            str(local_path),
            self._b2_bucket_name,
            b2_key,
            Config=self._transfer_config,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable_http_error),
        reraise=True,
    )
    def download_file(self, b2_key: str, local_path: Path) -> None:
        encoded_key = quote(b2_key.lstrip("/"), safe="/")
        url = f"{self._cf_worker_url}/files/{encoded_key}"
        headers = {"Authorization": f"Bearer {self._cf_bearer_token}"}

        local_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            with local_path.open("wb") as file_obj:
                for chunk in response.iter_bytes():
                    file_obj.write(chunk)

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._b2_bucket_name, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys
