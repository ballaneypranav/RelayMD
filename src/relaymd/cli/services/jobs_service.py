from __future__ import annotations

import json
import tempfile
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
        validated_relative_path = _validate_relative_path(relative_path)
        manifest = self._download_checkpoint_manifest(job_id=job_id)
        files = _parse_manifest_files(manifest)
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
        files = _parse_manifest_files(manifest)

        results: list[dict[str, object]] = []
        failed_files = 0
        downloaded_files = 0
        total_bytes = 0

        for relative_path in sorted(files.keys()):
            entry = files[relative_path]
            if not isinstance(entry, dict):
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": "",
                        "local_path": "",
                        "bytes": 0,
                        "error": "Manifest file entry is not an object",
                    }
                )
                continue
            remote_key = entry.get("remote_key")
            if not isinstance(remote_key, str) or not remote_key:
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": "",
                        "local_path": "",
                        "bytes": 0,
                        "error": "Manifest file entry has invalid remote_key",
                    }
                )
                continue

            local_path = base_output_dir / "files" / relative_path
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                self._context.storage_client().download_file(remote_key, local_path)
                file_size = local_path.stat().st_size
            except Exception as exc:  # noqa: BLE001
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": remote_key,
                        "local_path": str(local_path),
                        "bytes": 0,
                        "error": str(exc),
                    }
                )
                continue

            downloaded_files += 1
            total_bytes += file_size
            results.append(
                {
                    "relative_path": relative_path,
                    "remote_key": remote_key,
                    "local_path": str(local_path),
                    "bytes": file_size,
                }
            )

        return {
            "job_id": str(job_id),
            "manifest_path": str(manifest_local_path),
            "output_dir": str(base_output_dir),
            "status": "partial_failure" if failed_files > 0 else "success",
            "downloaded_files": downloaded_files,
            "failed_files": failed_files,
            "total_files": len(files),
            "total_bytes": total_bytes,
            "results": results,
        }

    def _latest_checkpoint_key(self, job: JobRead) -> str:
        if not job.latest_checkpoint_path:
            raise RuntimeError(json_dumps_error("no_checkpoint", "Job has no checkpoint yet"))
        return job.latest_checkpoint_path

    def _download_checkpoint_manifest(
        self, *, job_id: UUID, output_path: Path | None = None
    ) -> dict[str, object]:
        job = self.get_job(job_id=job_id)
        manifest_key = self._latest_checkpoint_key(job)
        if output_path is not None:
            manifest_local_path = output_path
            manifest_local_path.parent.mkdir(parents=True, exist_ok=True)
            self._context.storage_client().download_file(manifest_key, manifest_local_path)
        else:
            with tempfile.TemporaryDirectory(prefix="relaymd-manifest-") as tmpdir:
                manifest_local_path = Path(tmpdir) / "manifest.json"
                self._context.storage_client().download_file(manifest_key, manifest_local_path)
                try:
                    manifest = json.loads(manifest_local_path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        json_dumps_error(
                            "manifest_invalid", f"Failed to parse manifest JSON: {exc}"
                        )
                    ) from exc
                if not isinstance(manifest, dict):
                    raise RuntimeError(
                        json_dumps_error(
                            "manifest_invalid", "Checkpoint manifest must be a JSON object"
                        )
                    )
                return manifest

        try:
            manifest = json.loads(manifest_local_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                json_dumps_error("manifest_invalid", f"Failed to parse manifest JSON: {exc}")
            ) from exc
        if not isinstance(manifest, dict):
            raise RuntimeError(
                json_dumps_error("manifest_invalid", "Checkpoint manifest must be a JSON object")
            )
        return manifest


def json_dumps_error(code: str, message: str) -> str:
    return f'{{"error": {{"code": "{code}", "message": "{message}"}}}}'


def _validate_relative_path(value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeError(
            json_dumps_error("checkpoint_download_failed", "Path must be manifest-relative")
        )
    if value.strip() == "":
        raise RuntimeError(
            json_dumps_error("checkpoint_download_failed", "Path must be manifest-relative")
        )
    return candidate.as_posix()


def _parse_manifest_files(manifest: dict[str, object]) -> dict[str, object]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise RuntimeError(
            json_dumps_error(
                "manifest_invalid", "Checkpoint manifest is missing object field 'files'"
            )
        )
    return files
