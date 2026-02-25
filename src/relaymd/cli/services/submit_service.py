from __future__ import annotations

from pathlib import Path

from relaymd_api_client.api.default import create_job_jobs_post
from relaymd_api_client.models.job_create import JobCreate
from relaymd_api_client.models.job_read import JobRead

from relaymd.cli.context import CliContext


class SubmitService:
    def __init__(self, context: CliContext) -> None:
        self._context = context

    def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
        self._context.storage_client().upload_file(local_archive, b2_key)

    def register_job(self, *, title: str, b2_key: str) -> str:
        with self._context.api_client() as client:
            response = create_job_jobs_post.sync(
                client=client,
                body=JobCreate(title=title, input_bundle_path=b2_key),
                x_api_token=self._context.settings.api_token,
            )

        if response is None or not isinstance(response, JobRead):
            raise RuntimeError("Failed to parse create job response")
        return str(response.id)
