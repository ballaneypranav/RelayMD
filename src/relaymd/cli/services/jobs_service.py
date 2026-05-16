from __future__ import annotations

from pathlib import Path
from uuid import UUID

from relaymd_api_client.api.default import (
    cancel_job_jobs_job_id_delete,
    get_job_jobs_job_id_get,
    list_jobs_jobs_get,
    prune_jobs_jobs_delete,
    requeue_job_jobs_job_id_requeue_post,
)
from relaymd_api_client.models.http_validation_error import HTTPValidationError
from relaymd_api_client.models.job_conflict import JobConflict
from relaymd_api_client.models.job_read import JobRead
from relaymd_api_client.models.job_status import JobStatus as ClientJobStatus

from relaymd.cli.context import CliContext
from relaymd.cli.services._jobs_checkpoint_download import (
    download_all_checkpoint_materialized,
    json_dumps_error,
    parse_manifest_files,
    read_checkpoint_manifest,
    validate_relative_path,
)


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
        if isinstance(response, dict):
            raise RuntimeError(response)
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
        if isinstance(response, dict):
            raise RuntimeError(response)
        if isinstance(response, HTTPValidationError | JobConflict):
            raise RuntimeError(response.to_dict())
        if response is None or not isinstance(response, JobRead):
            raise RuntimeError("Failed to parse requeue response")
        return response

    def prune_jobs(self, *, statuses: list[str], older_than_days: int) -> int:
        status_enums = [ClientJobStatus(s) for s in statuses]
        with self._context.api_client() as client:
            response = prune_jobs_jobs_delete.sync(
                client=client,
                status=status_enums,
                older_than_days=older_than_days,
                x_api_token=self._context.settings.api_token,
            )
        if isinstance(response, dict):
            raise RuntimeError(response)
        if response is None:
            raise RuntimeError("Empty response from prune endpoint")
        return int(response["deleted"])

    def download_latest_checkpoint(self, *, job_id: UUID, output: Path | None) -> dict[str, object]:
        job = self.get_job(job_id=job_id)
        key = self._latest_checkpoint_key(job)
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

    def download_checkpoint_file(
        self, *, job_id: UUID, relative_path: str, output: Path | None
    ) -> dict[str, object]:
        validated_relative_path = validate_relative_path(relative_path)
        manifest = self._download_checkpoint_manifest(job_id=job_id)
        files = parse_manifest_files(manifest)
        entry = files.get(validated_relative_path)
        if not isinstance(entry, dict):
            raise RuntimeError(
                json_dumps_error(
                    "checkpoint_file_not_found",
                    f"Manifest path not found: {validated_relative_path}",
                )
            )
        remote_key = entry.get("remote_key")
        if not isinstance(remote_key, str) or not remote_key:
            raise RuntimeError(
                json_dumps_error("manifest_invalid", "Manifest file entry has invalid remote_key")
            )

        if output is None:
            local_path = Path.cwd() / f"{job_id}-checkpoint-files" / validated_relative_path
        elif output.exists() and output.is_dir():
            local_path = output / Path(validated_relative_path).name
        else:
            local_path = output

        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_client().download_file(remote_key, local_path)
        file_size = local_path.stat().st_size
        return {
            "job_id": str(job_id),
            "relative_path": validated_relative_path,
            "remote_key": remote_key,
            "local_path": str(local_path),
            "bytes": file_size,
        }

    def download_all_checkpoint_files(
        self, *, job_id: UUID, output_dir: Path | None
    ) -> dict[str, object]:
        base_output_dir = output_dir or (Path.cwd() / f"{job_id}-checkpoints")
        base_output_dir.mkdir(parents=True, exist_ok=True)
        manifest_local_path = base_output_dir / "manifest.json"
        manifest = self._download_checkpoint_manifest(
            job_id=job_id, output_path=manifest_local_path
        )
        return download_all_checkpoint_materialized(
            storage=self._context.storage_client(),
            job_id=job_id,
            base_output_dir=base_output_dir,
            manifest=manifest,
            manifest_local_path=manifest_local_path,
        )

    def _latest_checkpoint_key(self, job: JobRead) -> str:
        if not job.latest_checkpoint_manifest_path:
            raise RuntimeError(json_dumps_error("no_checkpoint", "Job has no checkpoint yet"))
        return job.latest_checkpoint_manifest_path

    def _download_checkpoint_manifest(
        self, *, job_id: UUID, output_path: Path | None = None
    ) -> dict[str, object]:
        job = self.get_job(job_id=job_id)
        manifest_key = self._latest_checkpoint_key(job)
        return read_checkpoint_manifest(
            storage=self._context.storage_client(),
            manifest_key=manifest_key,
            output_path=output_path,
        )
