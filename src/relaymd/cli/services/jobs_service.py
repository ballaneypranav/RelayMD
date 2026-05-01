from __future__ import annotations

from pathlib import Path
from uuid import UUID

from relaymd_api_client.api.default import (
    cancel_job_jobs_job_id_delete,
    get_job_jobs_job_id_get,
    list_jobs_jobs_get,
    requeue_job_jobs_job_id_requeue_post,
)
from relaymd_api_client.models.http_validation_error import HTTPValidationError
from relaymd_api_client.models.job_conflict import JobConflict
from relaymd_api_client.models.job_read import JobRead

from relaymd.cli.context import CliContext


class JobsService:
    def __init__(self, context: CliContext) -> None:
        self._context = context

    def list_jobs(self) -> list[JobRead]:
        with self._context.api_client() as client:
            jobs = list_jobs_jobs_get.sync(
                client=client,
                x_api_token=self._context.settings.api_token,
            )
        if jobs is None or not isinstance(jobs, list):
            raise RuntimeError("Failed to parse list jobs response")
        if jobs and not isinstance(jobs[0], JobRead):
            raise RuntimeError("Unexpected response model for list jobs")
        return jobs

    def get_job(self, *, job_id: UUID) -> JobRead:
        with self._context.api_client() as client:
            job = get_job_jobs_job_id_get.sync(
                job_id=job_id,
                client=client,
                x_api_token=self._context.settings.api_token,
            )
        if job is None or not isinstance(job, JobRead):
            raise RuntimeError("Failed to parse get job response")
        return job

    def cancel_job(self, *, job_id: UUID, force: bool) -> JobRead:
        with self._context.api_client() as client:
            response = cancel_job_jobs_job_id_delete.sync(
                job_id=job_id,
                client=client,
                force=force,
                x_api_token=self._context.settings.api_token,
            )
        if isinstance(response, HTTPValidationError | JobConflict):
            raise RuntimeError(response.to_dict())
        return self.get_job(job_id=job_id)

    def requeue_job(self, *, job_id: UUID) -> JobRead:
        with self._context.api_client() as client:
            response = requeue_job_jobs_job_id_requeue_post.sync(
                job_id=job_id,
                client=client,
                x_api_token=self._context.settings.api_token,
            )
        if isinstance(response, HTTPValidationError | JobConflict):
            raise RuntimeError(response.to_dict())
        if response is None or not isinstance(response, JobRead):
            raise RuntimeError("Failed to parse requeue response")
        return response

    def download_latest_checkpoint(self, *, job_id: UUID, output: Path | None) -> dict[str, object]:
        job = self.get_job(job_id=job_id)
        if not job.latest_checkpoint_path:
            raise RuntimeError(
                json_dumps_error("no_checkpoint", "Job has no checkpoint yet")
            )

        key = job.latest_checkpoint_path
        if output is None:
            local_path = Path.cwd() / f"{job_id}-checkpoint"
        elif output.exists() and output.is_dir():
            local_path = output / Path(key).name
        else:
            local_path = output

        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_client().download_file(key, local_path)
        file_size = local_path.stat().st_size
        return {
            "job_id": str(job_id),
            "checkpoint_path": key,
            "local_path": str(local_path),
            "bytes": file_size,
        }


def json_dumps_error(code: str, message: str) -> str:
    return f'{{"error": {{"code": "{code}", "message": "{message}"}}}}'
