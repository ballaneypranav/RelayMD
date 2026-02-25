from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import boto3
import httpx


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
        self._cf_worker_url = cf_worker_url.rstrip("/")
        self._cf_bearer_token = cf_bearer_token
        self._s3 = boto3.client(
            "s3",
            endpoint_url=b2_endpoint_url,
            aws_access_key_id=b2_access_key_id,
            aws_secret_access_key=b2_secret_access_key,
        )

    def upload_file(self, local_path: Path, b2_key: str) -> None:
        self._s3.upload_file(str(local_path), self._b2_bucket_name, b2_key)

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
        response = self._s3.list_objects_v2(Bucket=self._b2_bucket_name, Prefix=prefix)
        return [obj["Key"] for obj in response.get("Contents", [])]
