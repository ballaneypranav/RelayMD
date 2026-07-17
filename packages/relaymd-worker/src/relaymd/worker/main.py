from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import tarfile
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any, cast
from uuid import UUID

from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable
from relaymd_api_client.models.platform import Platform as ApiPlatform

from relaymd.models import Platform
from relaymd.storage import StorageClient
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.config import WorkerRuntimeSettings
from relaymd.worker.context import WorkerContext
from relaymd.worker.gateway import ApiOrchestratorGateway
from relaymd.worker.heartbeat import HeartbeatHealthSnapshot, HeartbeatThread
from relaymd.worker.job_execution import JobExecution
from relaymd.worker.logging import get_logger

LOG = get_logger(__name__)
PROCESS_EXIT_POLL_INTERVAL_SECONDS = 2.0
CHECKPOINT_MANIFEST_SCHEMA_VERSION = 1
CHECKPOINT_STATUS_SCHEMA_VERSION = 1
FAILURE_ARTIFACT_SCHEMA_VERSION = 1
CHECKPOINT_WATCH_FILE_CAP = 250
PROGRESS_ROLLBACK_TOLERANCE = 0.05
PROGRESS_MISSING = "progress_missing"
PROGRESS_EMPTY = "progress_empty"
PROGRESS_INVALID_FORMAT = "progress_invalid_format"
PROGRESS_OUT_OF_RANGE_CLAMPED = "progress_out_of_range_clamped"


@dataclass
class BundleExecutionConfig:
    command: list[str]
    checkpoint_watch_paths: list[str]
    resume_preserved_output_paths: list[str]
    progress_file_path: str
    failure_artifact_paths: list[str] = field(default_factory=list)
    checkpoint_poll_interval_seconds: int | None = None
    progress_glob_patterns: list[str] | None = None
    startup_progress_timeout_seconds: int | None = None
    progress_timeout_seconds: int | None = None
    max_runtime_seconds: int | None = None
    fatal_log_path: str | None = None
    fatal_log_patterns: list[str] | None = None


def _get_pynvml_module() -> ModuleType:
    import pynvml  # type: ignore[import-not-found]

    return pynvml


def detect_gpu_info() -> tuple[str, int, int]:
    try:
        pynvml = _get_pynvml_module()
        pynvml.nvmlInit()
        try:
            gpu_count = int(pynvml.nvmlDeviceGetCount())
            if gpu_count <= 0:
                return "unknown", 0, 0

            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            gpu_model = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_gb = int(memory_info.total / (1024**3))
            return gpu_model, gpu_count, vram_gb
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        LOG.exception("gpu_detection_failed_falling_back_to_defaults")
        return "unknown", 0, 0


def detect_openmm_platforms() -> list[str]:
    try:
        from openmm import Platform  # type: ignore[import-not-found]
    except Exception:
        LOG.exception("openmm_preflight_import_failed")
        return []

    try:
        return [Platform.getPlatform(i).getName() for i in range(Platform.getNumPlatforms())]
    except Exception:
        LOG.exception("openmm_preflight_platform_probe_failed")
        return []


_OPENMM_PLATFORM_RE = re.compile(r"^\s*OPENMM_PLATFORM\s*:\s*(\S+)", re.IGNORECASE)


def _required_openmm_platform(bundle_root: Path) -> str | None:
    """Return the OPENMM_PLATFORM value found in any bundle YAML, or None."""
    for yaml_file in sorted(bundle_root.rglob("*.yaml")) + sorted(bundle_root.rglob("*.yml")):
        try:
            for line in yaml_file.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _OPENMM_PLATFORM_RE.match(line)
                if m:
                    # Strip surrounding quotes if present and normalise to upper case
                    platform = m.group(1)
                    if (platform.startswith('"') and platform.endswith('"')) or (
                        platform.startswith("'") and platform.endswith("'")
                    ):
                        platform = platform[1:-1]
                    return platform.upper()
        except OSError:
            continue
    return None


def _load_bundle_execution_config(bundle_root: Path) -> BundleExecutionConfig:
    candidate_paths = [
        bundle_root / "relaymd-worker.json",
        bundle_root / "relaymd-worker.toml",
        bundle_root / "config.json",
        bundle_root / "config.toml",
    ]

    for extension in ("*.json", "*.toml"):
        candidate_paths.extend(sorted(bundle_root.rglob(extension)))

    seen: set[Path] = set()
    for path in candidate_paths:
        if path in seen or not path.exists() or not path.is_file():
            continue
        seen.add(path)

        parsed = _parse_bundle_config(path)
        if parsed is None:
            continue

        command_raw = parsed.get("command")
        if not command_raw:
            continue
        watch_paths = _required_string_list(parsed, "checkpoint_watch_paths")
        resume_preserved_output_paths = (
            _optional_string_list(parsed, "resume_preserved_output_paths") or []
        )
        _validate_resume_preserved_path_overlap(
            checkpoint_watch_paths=watch_paths,
            resume_preserved_output_paths=resume_preserved_output_paths,
        )
        progress_file_path = _required_string(parsed, "progress_file_path")

        if isinstance(command_raw, str):
            command = shlex.split(command_raw)
        elif isinstance(command_raw, list) and all(isinstance(item, str) for item in command_raw):
            command = command_raw
        else:
            continue

        if not command:
            continue
        bundle_interval = _optional_positive_int(
            parsed,
            "checkpoint_poll_interval_seconds",
        )
        startup_progress_timeout_seconds = _optional_positive_int(
            parsed,
            "startup_progress_timeout_seconds",
        )
        progress_timeout_seconds = _optional_positive_int(
            parsed,
            "progress_timeout_seconds",
        )
        max_runtime_seconds = _optional_positive_int(parsed, "max_runtime_seconds")
        progress_glob_patterns = _optional_string_list(parsed, "progress_glob_pattern")
        fatal_log_path = _optional_string(parsed, "fatal_log_path")
        fatal_log_patterns = _optional_string_list(parsed, "fatal_log_patterns")
        failure_artifact_paths = _optional_string_list(parsed, "failure_artifact_paths") or []

        return BundleExecutionConfig(
            command=command,
            checkpoint_watch_paths=watch_paths,
            resume_preserved_output_paths=resume_preserved_output_paths,
            progress_file_path=progress_file_path,
            failure_artifact_paths=failure_artifact_paths,
            checkpoint_poll_interval_seconds=bundle_interval,
            progress_glob_patterns=progress_glob_patterns,
            startup_progress_timeout_seconds=startup_progress_timeout_seconds,
            progress_timeout_seconds=progress_timeout_seconds,
            max_runtime_seconds=max_runtime_seconds,
            fatal_log_path=fatal_log_path,
            fatal_log_patterns=fatal_log_patterns,
        )

    raise RuntimeError("No valid worker bundle config found in input bundle")


def _optional_positive_int(parsed: dict[str, Any], key: str) -> int | None:
    value = parsed.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"Invalid {key} in bundle config")
    return value


def _optional_string(parsed: dict[str, Any], key: str) -> str | None:
    value = parsed.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid {key} in bundle config")
    return value


def _optional_string_list(parsed: dict[str, Any], key: str) -> list[str] | None:
    value = parsed.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            raise RuntimeError(f"Invalid {key} in bundle config")
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise RuntimeError(f"Invalid {key} in bundle config")


def _required_string_list(parsed: dict[str, Any], key: str) -> list[str]:
    value = parsed.get(key)
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise RuntimeError(f"Invalid {key} in bundle config")


def _required_string(parsed: dict[str, Any], key: str) -> str:
    value = parsed.get(key)
    if isinstance(value, str) and value:
        return value
    raise RuntimeError(f"Invalid {key} in bundle config")


def _validated_path_set(paths: list[str]) -> set[str]:
    validated: set[str] = set()
    for raw_path in paths:
        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError(f"Invalid path in bundle config: {raw_path}")
        validated.add(candidate.as_posix())
    return validated


def _validate_resume_preserved_path_overlap(
    *,
    checkpoint_watch_paths: list[str],
    resume_preserved_output_paths: list[str],
) -> None:
    watch_paths = _validated_path_set(checkpoint_watch_paths)
    resume_paths = _validated_path_set(resume_preserved_output_paths)
    overlap = sorted(watch_paths & resume_paths)
    if overlap:
        raise RuntimeError(
            "Invalid bundle config: paths cannot appear in both checkpoint_watch_paths "
            "and resume_preserved_output_paths"
        )


def _effective_checkpoint_watch_paths(execution_config: BundleExecutionConfig) -> list[str]:
    combined = (
        execution_config.checkpoint_watch_paths
        + [execution_config.progress_file_path]
        + execution_config.resume_preserved_output_paths
    )
    deduped: list[str] = []
    seen: set[str] = set()
    for raw_path in combined:
        normalized = Path(raw_path).as_posix()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(raw_path)
    return deduped


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _local_manifest_path(workdir: Path) -> Path:
    return workdir / "relaymd-checkpoint-manifest.json"


def _empty_manifest(job_id: str) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "schema_version": CHECKPOINT_MANIFEST_SCHEMA_VERSION,
        "job_id": job_id,
        "updated_at": now,
        "cycle_summary": {
            "cycle_started_at": now,
            "cycle_finished_at": now,
            "matched_files": 0,
            "processed_files": 0,
            "uploaded_files": 0,
            "unchanged_files": 0,
            "deleted_files": 0,
            "failed_files": 0,
            "status": "empty",
        },
        "files": {},
        "failures": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _checkpoint_manifest_key(job_id: UUID) -> str:
    return f"jobs/{job_id}/checkpoints/manifest.json"


def _checkpoint_file_key(job_id: UUID, relative_path: str) -> str:
    return f"jobs/{job_id}/checkpoints/files/{relative_path}"


def _checkpoint_status_key(job_id: UUID) -> str:
    return f"jobs/{job_id}/checkpoints/status.json"


def _checkpoint_preserved_output_key(job_id: UUID, relative_path: str, resume_segment: int) -> str:
    return f"jobs/{job_id}/checkpoints/preserved-output/{relative_path}/{resume_segment:04d}"


def _parse_bundle_config(path: Path) -> dict[str, Any] | None:
    try:
        if path.suffix == ".json":
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        elif path.suffix == ".toml":
            with path.open("rb") as file_obj:
                data = tomllib.load(file_obj)
        else:
            return None
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    return data


def _extract_input_bundle(bundle_file: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(bundle_file):
        with tarfile.open(bundle_file, "r:*") as archive:
            try:
                archive.extractall(destination, filter="data")
            except TypeError as err:
                destination_abs = destination.resolve()
                for member in archive.getmembers():
                    if member.issym() or member.islnk():
                        raise RuntimeError(
                            "Input bundle must not contain symlinks or hard links"
                        ) from err
                    member_target = (destination / member.name).resolve()
                    if (
                        member_target != destination_abs
                        and destination_abs not in member_target.parents
                    ):
                        raise RuntimeError("Input bundle contains path traversal entries") from err
                archive.extractall(destination)
        return destination

    copied_path = destination / bundle_file.name
    copied_path.write_bytes(bundle_file.read_bytes())
    return destination


def _build_storage_client(
    config: WorkerConfig,
    runtime_settings: WorkerRuntimeSettings,
) -> StorageClient:
    if runtime_settings.storage_provider == "purdue":
        missing: list[str] = []
        if not config.purdue_s3_endpoint.strip():
            missing.append("PURDUE_S3_ENDPOINT")
        if not config.purdue_s3_bucket_name.strip():
            missing.append("PURDUE_S3_BUCKET_NAME")
        if not config.purdue_s3_access_key.strip():
            missing.append("PURDUE_S3_ACCESS_KEY")
        if not config.purdue_s3_secret_key.strip():
            missing.append("PURDUE_S3_SECRET_KEY")
        if missing:
            missing_text = ", ".join(missing)
            raise RuntimeError(
                "Missing required Purdue S3 bootstrap secrets: "
                f"{missing_text}. Configure these in Infisical."
            )
        return StorageClient(
            storage_provider="purdue",
            b2_endpoint_url=config.purdue_s3_endpoint,
            b2_bucket_name=config.purdue_s3_bucket_name,
            b2_access_key_id=config.purdue_s3_access_key,
            b2_secret_access_key=config.purdue_s3_secret_key,
            cf_worker_url=runtime_settings.cf_worker_url,
            cf_bearer_token="",
            s3_region_name="us-east-1",
        )

    cf_bearer_token = (
        config.download_bearer_token or runtime_settings.cf_bearer_token or config.relaymd_api_token
    )
    return StorageClient(
        storage_provider="cloudflare_backblaze",
        b2_endpoint_url=config.b2_endpoint,
        b2_bucket_name=config.bucket_name,
        b2_access_key_id=config.b2_application_key_id,
        b2_secret_access_key=config.b2_application_key,
        cf_worker_url=runtime_settings.cf_worker_url,
        cf_bearer_token=cf_bearer_token,
        s3_region_name=None,
    )


def _load_persisted_manifest(
    *, context: WorkerContext, logger, job_id: UUID, workdir: Path
) -> dict[str, Any]:
    manifest_key = _checkpoint_manifest_key(job_id)
    manifest_path = _local_manifest_path(workdir)
    empty = _empty_manifest(str(job_id))
    try:
        context.storage.download_file(manifest_key, manifest_path)
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        logger.warning("checkpoint_manifest_remote_unavailable_fallback")

    if manifest_path.is_file():
        try:
            parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            logger.warning("checkpoint_manifest_local_invalid_fallback")
    return empty


def _resolve_hydration_destination(*, bundle_root: Path, relative_path: str) -> Path:
    raw_relative = Path(relative_path)
    if raw_relative.is_absolute() or ".." in raw_relative.parts:
        raise RuntimeError("invalid_relative_path")

    bundle_root_resolved = bundle_root.resolve()
    destination = bundle_root / raw_relative
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)

    current = bundle_root_resolved
    for part in raw_relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise RuntimeError("unsafe_symlink_in_destination_path")
    if destination.exists() and destination.is_symlink():
        raise RuntimeError("unsafe_symlink_destination")

    destination_resolved = destination.resolve(strict=False)
    if destination_resolved != bundle_root_resolved and bundle_root_resolved not in (
        destination_resolved.parents
    ):
        raise RuntimeError("destination_outside_bundle_root")
    return destination


def _hydrate_checkpoint_files_from_manifest(
    *,
    context: WorkerContext,
    logger,
    job_id: UUID,
    bundle_root: Path,
    manifest: dict[str, Any],
) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("invalid_manifest_files")

    logger.info("checkpoint_hydration_started", job_id=str(job_id))
    for relative_path, file_entry in sorted(files.items()):
        if not isinstance(relative_path, str) or not relative_path:
            raise RuntimeError("invalid_manifest_relative_path")
        if not isinstance(file_entry, dict):
            raise RuntimeError("invalid_manifest_file_entry")

        remote_key = file_entry.get("remote_key")
        if not isinstance(remote_key, str) or not remote_key:
            raise RuntimeError("invalid_manifest_remote_key")

        destination = _resolve_hydration_destination(
            bundle_root=bundle_root,
            relative_path=relative_path,
        )
        context.storage.download_file(remote_key, destination)
        logger.info(
            "checkpoint_file_hydrated",
            job_id=str(job_id),
            relative_path=relative_path,
            remote_key=remote_key,
        )

    logger.info("checkpoint_hydration_completed", job_id=str(job_id))


def _next_resume_segment(manifest: dict[str, Any]) -> int:
    preserved_outputs = manifest.get("preserved_outputs")
    if not isinstance(preserved_outputs, dict):
        return 1
    max_segment = 0
    for entry in preserved_outputs.values():
        if not isinstance(entry, dict):
            continue
        snapshots = entry.get("snapshots")
        if not isinstance(snapshots, list):
            continue
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            segment = snapshot.get("resume_segment")
            if isinstance(segment, int) and segment > max_segment:
                max_segment = segment
    return max_segment + 1


def _capture_resume_preserved_outputs(
    *,
    context: WorkerContext,
    logger,
    job_id: UUID,
    workdir: Path,
    manifest: dict[str, Any],
    resume_preserved_output_paths: list[str],
) -> None:
    if not resume_preserved_output_paths:
        return

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("invalid_manifest_files")

    preserved_outputs = manifest.get("preserved_outputs")
    if not isinstance(preserved_outputs, dict):
        preserved_outputs = {}
        manifest["preserved_outputs"] = preserved_outputs

    resume_segment = _next_resume_segment(manifest)
    for relative_path in sorted(_validated_path_set(resume_preserved_output_paths)):
        file_entry = files.get(relative_path)
        if not isinstance(file_entry, dict):
            logger.info(
                "checkpoint_preserved_output_skipped_missing_live_file",
                job_id=str(job_id),
                relative_path=relative_path,
            )
            continue
        remote_key = file_entry.get("remote_key")
        if not isinstance(remote_key, str) or not remote_key:
            raise RuntimeError("invalid_manifest_remote_key")

        staging_path = workdir / "preserved-output-staging" / relative_path
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage.download_file(remote_key, staging_path)

        sha256 = _compute_sha256(staging_path)
        size_bytes = staging_path.stat().st_size
        preserved_remote_key = _checkpoint_preserved_output_key(
            job_id=job_id,
            relative_path=relative_path,
            resume_segment=resume_segment,
        )
        context.storage.upload_file(staging_path, preserved_remote_key)

        path_entry_raw = preserved_outputs.get(relative_path)
        path_entry: dict[str, Any]
        if isinstance(path_entry_raw, dict):
            path_entry = path_entry_raw
        else:
            path_entry = {}
            preserved_outputs[relative_path] = path_entry
        snapshots_raw = path_entry.get("snapshots")
        snapshots: list[dict[str, Any]]
        if isinstance(snapshots_raw, list):
            snapshots = [item for item in snapshots_raw if isinstance(item, dict)]
        else:
            snapshots = []
        snapshots.append(
            {
                "resume_segment": resume_segment,
                "remote_key": preserved_remote_key,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "captured_at": _utc_now_iso(),
            }
        )
        path_entry["snapshots"] = snapshots
        logger.info(
            "checkpoint_preserved_output_captured",
            job_id=str(job_id),
            relative_path=relative_path,
            resume_segment=resume_segment,
            remote_key=preserved_remote_key,
        )


def _resolve_watch_files(
    *, bundle_root: Path, watch_paths: list[str]
) -> tuple[list[Path], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    unique: dict[str, Path] = {}
    root_resolved = bundle_root.resolve()
    for pattern in watch_paths:
        raw = Path(pattern)
        if raw.is_absolute() or ".." in raw.parts:
            failures.append(
                {"code": "path_validation_failed", "detail": f"invalid watch path: {pattern}"}
            )
            continue
        for path in bundle_root.glob(pattern):
            try:
                resolved = path.resolve()
                if root_resolved not in resolved.parents and resolved != root_resolved:
                    failures.append(
                        {"code": "path_validation_failed", "detail": f"path traversal: {path}"}
                    )
                    continue
                if path.is_symlink():
                    failures.append(
                        {"code": "path_validation_failed", "detail": f"symlink not allowed: {path}"}
                    )
                    continue
                stat_result = path.stat()
                if not path.is_file() or not resolved.is_file():
                    failures.append(
                        {"code": "path_validation_failed", "detail": f"not a regular file: {path}"}
                    )
                    continue
                _ = stat_result
                relative = str(path.relative_to(bundle_root)).replace(os.sep, "/")
                unique[relative] = path
            except OSError:
                failures.append(
                    {"code": "path_validation_failed", "detail": f"unreadable path: {path}"}
                )
    return [unique[key] for key in sorted(unique)], failures


def _read_progress(*, bundle_root: Path, progress_file_path: str) -> tuple[float, list[str]]:
    progress_path = bundle_root / progress_file_path
    if Path(progress_file_path).is_absolute() or ".." in Path(progress_file_path).parts:
        return 0.0, [PROGRESS_INVALID_FORMAT]
    if not progress_path.exists():
        return 0.0, [PROGRESS_MISSING]

    text = progress_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return 0.0, [PROGRESS_EMPTY]

    parts = text.split()
    if len(parts) != 1:
        return 0.0, [PROGRESS_INVALID_FORMAT]
    try:
        progress = float(parts[0])
    except ValueError:
        return 0.0, [PROGRESS_INVALID_FORMAT]

    codes: list[str] = []
    if progress < 0.0 or progress > 1.0:
        progress = max(0.0, min(1.0, progress))
        codes.append(PROGRESS_OUT_OF_RANGE_CLAMPED)
    return progress, codes


def _parse_proactive_handoff_trigger() -> tuple[float | None, float | None]:
    deadline_raw = os.environ.get("RELAYMD_ALLOCATION_DEADLINE_EPOCH_SECONDS")
    margin_raw = os.environ.get("RELAYMD_PROACTIVE_HANDOFF_MARGIN_SECONDS")
    if not deadline_raw or not margin_raw:
        return None, None
    try:
        deadline = float(deadline_raw)
        margin = float(margin_raw)
    except ValueError:
        return None, None
    if margin < 0:
        return None, None
    return max(0.0, deadline - margin), deadline


def _sync_checkpoint_manifest_cycle(
    *,
    context: WorkerContext,
    logger,
    job_id: UUID,
    bundle_root: Path,
    workdir: Path,
    watch_paths: list[str],
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    logger.info("checkpoint_cycle_started")
    cycle_started_at = _utc_now_iso()
    files_state = manifest.get("files", {})
    if not isinstance(files_state, dict):
        files_state = {}
    failures: list[dict[str, str]] = []
    matched_files, resolve_failures = _resolve_watch_files(
        bundle_root=bundle_root, watch_paths=watch_paths
    )
    failures.extend(resolve_failures)

    processed_files = 0
    uploaded_files = 0
    unchanged_files = 0
    failed_files = len(resolve_failures)
    manifest.pop("_preserve_existing_files_once", None)

    matched_files_count = len(matched_files)
    if matched_files_count > CHECKPOINT_WATCH_FILE_CAP:
        failures.append(
            {"code": "watch_file_cap_exceeded", "detail": f"matched_files={matched_files_count}"}
        )
        failed_files += 1
        matched_files = []

    def _record_file_failure(relative_path: str, code: str, detail: str) -> None:
        nonlocal failed_files
        failures.append({"code": code, "detail": detail})
        failed_files += 1
        now = _utc_now_iso()
        previous = files_state.get(relative_path)
        if isinstance(previous, dict):
            updated = dict(previous)
            updated["last_seen_at"] = now
            updated["last_failure_at"] = now
            updated["last_failure_code"] = code
            files_state[relative_path] = updated
        logger.warning("checkpoint_file_failed", code=code, relative_path=relative_path)

    for file_path in matched_files:
        processed_files += 1
        relative_path = str(file_path.relative_to(bundle_root)).replace(os.sep, "/")
        file_state = files_state.get(relative_path, {})
        try:
            stat_result = file_path.stat()
        except FileNotFoundError:
            _record_file_failure(relative_path, "file_disappeared", relative_path)
            continue

        if (
            isinstance(file_state, dict)
            and file_state.get("size_bytes") == stat_result.st_size
            and file_state.get("mtime_ns") == stat_result.st_mtime_ns
        ):
            unchanged_files += 1
            continue

        stage_path = workdir / "checkpoint-staging" / relative_path
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            source_hash_before = _compute_sha256(file_path)
        except Exception:
            _record_file_failure(relative_path, "source_hash_failed", relative_path)
            continue
        try:
            shutil.copy2(file_path, stage_path)
        except Exception:
            _record_file_failure(relative_path, "staging_copy_failed", relative_path)
            continue
        try:
            source_hash_after = _compute_sha256(file_path)
        except Exception:
            _record_file_failure(relative_path, "source_hash_failed", relative_path)
            continue
        try:
            staged_hash = _compute_sha256(stage_path)
        except Exception:
            _record_file_failure(relative_path, "staged_hash_failed", relative_path)
            continue
        if source_hash_before != source_hash_after:
            _record_file_failure(relative_path, "potential_write_in_progress", relative_path)
            continue
        if source_hash_before != staged_hash:
            _record_file_failure(relative_path, "staged_hash_failed", relative_path)
            continue

        remote_key = _checkpoint_file_key(job_id, relative_path)
        try:
            context.storage.upload_file(stage_path, remote_key)
        except Exception:
            _record_file_failure(relative_path, "upload_failed", relative_path)
            continue
        now = _utc_now_iso()
        files_state[relative_path] = {
            "sha256": staged_hash,
            "size_bytes": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
            "remote_key": remote_key,
            "last_seen_at": now,
            "last_upload_at": now,
            "last_failure_at": None,
            "last_failure_code": None,
        }
        uploaded_files += 1
        logger.info("checkpoint_file_uploaded", relative_path=relative_path, remote_key=remote_key)

    status = "success"
    if failures and uploaded_files > 0:
        status = "partial_failure"
    elif failures:
        status = "failed"

    cycle_finished_at = _utc_now_iso()
    manifest["schema_version"] = CHECKPOINT_MANIFEST_SCHEMA_VERSION
    manifest["job_id"] = str(job_id)
    manifest["updated_at"] = cycle_finished_at
    manifest["files"] = files_state
    manifest["cycle_summary"] = {
        "cycle_started_at": cycle_started_at,
        "cycle_finished_at": cycle_finished_at,
        "matched_files": matched_files_count,
        "processed_files": processed_files,
        "uploaded_files": uploaded_files,
        "unchanged_files": unchanged_files,
        "deleted_files": 0,
        "failed_files": failed_files,
        "status": status,
    }
    manifest["failures"] = failures

    manifest_path = _local_manifest_path(workdir)
    _atomic_write_json(manifest_path, manifest)
    manifest_key = _checkpoint_manifest_key(job_id)
    try:
        context.storage.upload_file(manifest_path, manifest_key)
    except Exception:
        logger.exception("checkpoint_cycle_failed", checkpoint_manifest_key=manifest_key)
        manifest["failures"] = failures + [
            {"code": "manifest_upload_failed", "detail": manifest_key}
        ]
        manifest["cycle_summary"]["status"] = "failed"
        manifest["cycle_summary"]["failed_files"] = manifest["cycle_summary"]["failed_files"] + 1
        _atomic_write_json(manifest_path, manifest)
        return manifest, False

    if status == "success":
        logger.info("checkpoint_cycle_completed", checkpoint_manifest_key=manifest_key)
    elif status == "partial_failure":
        logger.warning("checkpoint_cycle_partial_failure", checkpoint_manifest_key=manifest_key)
    else:
        logger.warning("checkpoint_cycle_failed", checkpoint_manifest_key=manifest_key)
    return manifest, True


def _checkpoint_diagnostics_from_manifest(
    manifest: dict[str, Any],
) -> tuple[str | None, list[dict[str, str]]]:
    status: str | None = None
    cycle_summary = manifest.get("cycle_summary")
    if isinstance(cycle_summary, dict):
        raw_status = cycle_summary.get("status")
        if isinstance(raw_status, str):
            status = raw_status

    failures: list[dict[str, str]] = []
    raw_failures = manifest.get("failures")
    if isinstance(raw_failures, list):
        for item in raw_failures:
            if isinstance(item, dict):
                failures.append(
                    {
                        "code": str(item.get("code", "")),
                        "detail": str(item.get("detail", "")),
                    }
                )
    return status, failures


def _upload_checkpoint_status(
    *,
    context: WorkerContext,
    assignment: ApiJobAssigned,
    workdir: Path,
    checkpoint_manifest_key: str,
    checkpoint_poll_interval_seconds: int,
    progress: float,
    progress_codes: list[str],
    checkpoint_cycle_status: str,
) -> bool:
    payload = {
        "schema_version": CHECKPOINT_STATUS_SCHEMA_VERSION,
        "job_id": str(assignment.job_id),
        "worker_id": str(context.worker_id) if context.worker_id is not None else None,
        "provider_id": context.provider_id,
        "updated_at": _utc_now_iso(),
        "checkpoint_manifest_path": checkpoint_manifest_key,
        "checkpoint_poll_interval_seconds": checkpoint_poll_interval_seconds,
        "progress": progress,
        "progress_codes": progress_codes,
        "checkpoint_cycle_status": checkpoint_cycle_status,
    }
    status_path = workdir / "relaymd-checkpoint-status.json"
    _atomic_write_json(status_path, payload)
    try:
        context.storage.upload_file(status_path, _checkpoint_status_key(assignment.job_id))
    except Exception:
        context.logger.warning(
            "checkpoint_status_upload_failed",
            job_id=str(assignment.job_id),
        )
        return False
    return True


def _report_checkpoint_best_effort(
    *,
    context: WorkerContext,
    assignment: ApiJobAssigned,
    checkpoint_manifest_key: str,
    progress: float,
    progress_codes: list[str],
    checkpoint_cycle_status: str | None,
    checkpoint_cycle_failures: list[dict[str, str]],
) -> None:
    try:
        context.gateway.report_checkpoint(
            job_id=assignment.job_id,
            checkpoint_manifest_path=checkpoint_manifest_key,
            checkpoint_path=checkpoint_manifest_key,
            progress=progress,
            progress_codes=progress_codes,
            checkpoint_cycle_status=checkpoint_cycle_status,
            checkpoint_cycle_failures=checkpoint_cycle_failures,
        )
    except Exception:
        context.logger.warning(
            "checkpoint_report_api_failed_continuing",
            job_id=str(assignment.job_id),
            checkpoint_manifest_path=checkpoint_manifest_key,
        )


def _fatal_log_artifact(bundle_root: Path, execution_config: BundleExecutionConfig) -> Path | None:
    if execution_config.fatal_log_path is None:
        return None

    path = bundle_root / execution_config.fatal_log_path
    if not path.is_file():
        return None
    return path


def _failure_artifact_key(job_id: UUID, failure_id: str, relative_path: str) -> str:
    return f"jobs/{job_id}/failures/{failure_id}/files/{relative_path}"


def _upload_failure_artifact(
    *,
    context: WorkerContext,
    logger,
    assignment: ApiJobAssigned,
    bundle_root: Path,
    workdir: Path,
    execution_config: BundleExecutionConfig,
    reason: str,
    detail: str | None,
    progress: float,
    progress_codes: list[str],
    resume_progress_baseline: float | None,
    checkpoint_manifest_path: str | None,
) -> str | None:
    worker_suffix = str(context.worker_id) if context.worker_id is not None else "unknown-worker"
    failure_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{worker_suffix}"
    base_path = f"jobs/{assignment.job_id}/failures/{failure_id}"
    files, resolve_failures = _resolve_watch_files(
        bundle_root=bundle_root, watch_paths=execution_config.failure_artifact_paths
    )
    file_records: list[dict[str, Any]] = []
    upload_failures: list[dict[str, str]] = [
        {"code": item.get("code", ""), "detail": item.get("detail", "")}
        for item in resolve_failures
    ]
    for path in files:
        relative_path = str(path.relative_to(bundle_root)).replace(os.sep, "/")
        remote_key = _failure_artifact_key(assignment.job_id, failure_id, relative_path)
        try:
            context.storage.upload_file(path, remote_key)
            file_records.append(
                {
                    "relative_path": relative_path,
                    "remote_key": remote_key,
                    "size_bytes": path.stat().st_size,
                    "sha256": _compute_sha256(path),
                    "captured_at": _utc_now_iso(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            upload_failures.append(
                {"code": "upload_failed", "detail": f"{relative_path}: {type(exc).__name__}"}
            )
            logger.warning("failure_artifact_file_upload_failed", relative_path=relative_path)

    diagnostics = {
        "job_id": str(assignment.job_id),
        "worker_id": str(context.worker_id) if context.worker_id is not None else None,
        "provider_id": context.provider_id,
        "reason": reason,
        "detail": detail,
        "progress": progress,
        "progress_codes": progress_codes,
        "resume_progress_baseline": resume_progress_baseline,
        "progress_regression_tolerance": PROGRESS_ROLLBACK_TOLERANCE,
        "checkpoint_manifest_path": checkpoint_manifest_path,
        "latest_checkpoint_manifest_path": checkpoint_manifest_path,
        "failure_artifact_paths": execution_config.failure_artifact_paths,
        "fatal_log_path": execution_config.fatal_log_path,
        "created_at": _utc_now_iso(),
    }
    diagnostics_path = workdir / "relaymd-failure-diagnostics.json"
    _atomic_write_json(diagnostics_path, diagnostics)
    diagnostics_key = f"{base_path}/diagnostics.json"
    try:
        context.storage.upload_file(diagnostics_path, diagnostics_key)
    except Exception:
        logger.warning("failure_artifact_diagnostics_upload_failed", key=diagnostics_key)
        upload_failures.append({"code": "diagnostics_upload_failed", "detail": diagnostics_key})

    failure_artifact_path = f"{base_path}/manifest.json"
    manifest = {
        "schema_version": FAILURE_ARTIFACT_SCHEMA_VERSION,
        "job_id": str(assignment.job_id),
        "worker_id": str(context.worker_id) if context.worker_id is not None else None,
        "provider_id": context.provider_id,
        "created_at": _utc_now_iso(),
        "reason": reason,
        "detail": detail,
        "failure_artifact_path": failure_artifact_path,
        "files": file_records,
        "upload_failures": upload_failures,
    }
    manifest_path = workdir / "relaymd-failure-manifest.json"
    _atomic_write_json(manifest_path, manifest)
    try:
        context.storage.upload_file(manifest_path, failure_artifact_path)
    except Exception:
        logger.warning("failure_artifact_manifest_upload_failed", key=failure_artifact_path)
        return None
    return failure_artifact_path


def _fail_assigned_job(
    *,
    context: WorkerContext,
    logger,
    assignment: ApiJobAssigned,
    bundle_root: Path,
    workdir: Path,
    execution_config: BundleExecutionConfig,
    reason: str,
    detail: str | None,
    progress: float,
    progress_codes: list[str],
    resume_progress_baseline: float | None,
    checkpoint_manifest_path: str | None,
) -> None:
    failure_artifact_path = _upload_failure_artifact(
        context=context,
        logger=logger,
        assignment=assignment,
        bundle_root=bundle_root,
        workdir=workdir,
        execution_config=execution_config,
        reason=reason,
        detail=detail,
        progress=progress,
        progress_codes=progress_codes,
        resume_progress_baseline=resume_progress_baseline,
        checkpoint_manifest_path=checkpoint_manifest_path,
    )
    context.gateway.fail_job(
        job_id=assignment.job_id,
        failure_artifact_path=failure_artifact_path,
        reason=reason,
        detail=detail,
    )


def _run_assigned_job(
    *,
    context: WorkerContext,
    assignment: ApiJobAssigned,
) -> bool:
    job_log = context.logger.bind(job_id=str(assignment.job_id))
    checkpoint_manifest_key = _checkpoint_manifest_key(assignment.job_id)

    with tempfile.TemporaryDirectory(prefix=f"relaymd-{assignment.job_id}-") as tmpdir:
        workdir = Path(tmpdir)
        input_bundle_path = workdir / Path(assignment.input_bundle_path).name
        context.storage.download_file(assignment.input_bundle_path, input_bundle_path)

        bundle_root = _extract_input_bundle(input_bundle_path, workdir / "bundle")

        execution_config = _load_bundle_execution_config(bundle_root)
        checkpoint_manifest = _load_persisted_manifest(
            context=context,
            logger=job_log,
            job_id=assignment.job_id,
            workdir=workdir,
        )
        checkpoint_manifest_path = getattr(assignment, "latest_checkpoint_manifest_path", None)
        resume_progress_baseline: float | None = None
        if checkpoint_manifest_path:
            try:
                _capture_resume_preserved_outputs(
                    context=context,
                    logger=job_log,
                    job_id=assignment.job_id,
                    workdir=workdir,
                    manifest=checkpoint_manifest,
                    resume_preserved_output_paths=execution_config.resume_preserved_output_paths,
                )
                _hydrate_checkpoint_files_from_manifest(
                    context=context,
                    logger=job_log,
                    job_id=assignment.job_id,
                    bundle_root=bundle_root,
                    manifest=checkpoint_manifest,
                )
                checkpoint_manifest["_preserve_existing_files_once"] = True
                resumed_progress, resumed_progress_codes = _read_progress(
                    bundle_root=bundle_root,
                    progress_file_path=execution_config.progress_file_path,
                )
                if not resumed_progress_codes:
                    resume_progress_baseline = resumed_progress
            except Exception as exc:
                job_log.warning(
                    "checkpoint_hydration_failed",
                    job_id=str(assignment.job_id),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                _fail_assigned_job(
                    context=context,
                    logger=job_log,
                    assignment=assignment,
                    bundle_root=bundle_root,
                    workdir=workdir,
                    execution_config=execution_config,
                    reason="checkpoint_hydration_failed",
                    detail=str(exc),
                    progress=0.0,
                    progress_codes=[PROGRESS_MISSING],
                    resume_progress_baseline=resume_progress_baseline,
                    checkpoint_manifest_path=checkpoint_manifest_path,
                )
                return False

        required_platform = _required_openmm_platform(bundle_root)
        if required_platform is not None and required_platform not in context.openmm_platforms:
            job_log.warning(
                "openmm_platform_unavailable",
                required_platform=required_platform,
                available_platforms=context.openmm_platforms,
            )
            _fail_assigned_job(
                context=context,
                logger=job_log,
                assignment=assignment,
                bundle_root=bundle_root,
                workdir=workdir,
                execution_config=execution_config,
                reason="openmm_platform_unavailable",
                detail=f"required={required_platform}",
                progress=0.0,
                progress_codes=[PROGRESS_MISSING],
                resume_progress_baseline=resume_progress_baseline,
                checkpoint_manifest_path=checkpoint_manifest_path,
            )
            return False

        execution = JobExecution(
            command=execution_config.command,
            workdir=bundle_root,
            checkpoint_glob_pattern="__unused__",
            checkpoint_b2_key="__unused__",
            progress_glob_patterns=execution_config.progress_glob_patterns,
            startup_progress_timeout_seconds=(execution_config.startup_progress_timeout_seconds),
            progress_timeout_seconds=execution_config.progress_timeout_seconds,
            max_runtime_seconds=execution_config.max_runtime_seconds,
            fatal_log_path=execution_config.fatal_log_path,
            fatal_log_patterns=execution_config.fatal_log_patterns,
        )
        try:
            execution.start()
            context.gateway.start_job(job_id=assignment.job_id)
            should_exit_loop = False
            handoff_completed = False
            degraded_mode_active = False
            degraded_mode_grace_logged = False
            heartbeat_grace_seconds = max(
                float(
                    context.heartbeat_failure_grace_multiplier * context.heartbeat_interval_seconds
                ),
                float(context.heartbeat_failure_grace_floor_seconds),
            )

            effective_checkpoint_poll_interval_seconds = (
                execution_config.checkpoint_poll_interval_seconds
                if execution_config.checkpoint_poll_interval_seconds is not None
                else context.checkpoint_poll_interval_seconds
            )
            job_log.info(
                "checkpoint_poll_interval_resolved",
                checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                source=(
                    "bundle"
                    if execution_config.checkpoint_poll_interval_seconds is not None
                    else "runtime_default"
                ),
            )
            checkpoint_poll_interval_seconds = float(effective_checkpoint_poll_interval_seconds)
            checkpoint_health_threshold_seconds = max(0.0, checkpoint_poll_interval_seconds * 3.0)
            next_checkpoint_poll_time = time.monotonic()
            handoff_trigger_time, handoff_deadline = _parse_proactive_handoff_trigger()
            last_checkpoint_storage_success_at: float | None = None
            latest_progress = 0.0
            latest_progress_codes = [PROGRESS_MISSING]
            while True:
                latest_progress, latest_progress_codes = _read_progress(
                    bundle_root=bundle_root,
                    progress_file_path=execution_config.progress_file_path,
                )
                if context.heartbeat_thread is not None:
                    context.heartbeat_thread.set_job_progress(
                        job_id=assignment.job_id,
                        progress=latest_progress,
                        progress_codes=latest_progress_codes,
                    )
                if context.shutdown_event.is_set():
                    job_log.info("shutdown_requested_terminating_job")
                    execution.request_terminate()
                    checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                        context=context,
                        logger=job_log,
                        job_id=assignment.job_id,
                        bundle_root=bundle_root,
                        workdir=workdir,
                        watch_paths=_effective_checkpoint_watch_paths(execution_config),
                        manifest=checkpoint_manifest,
                    )
                    if manifest_uploaded:
                        checkpoint_cycle_status, checkpoint_cycle_failures = (
                            _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                        )
                        status_uploaded = _upload_checkpoint_status(
                            context=context,
                            assignment=assignment,
                            workdir=workdir,
                            checkpoint_manifest_key=checkpoint_manifest_key,
                            checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                        )
                        _report_checkpoint_best_effort(
                            context=context,
                            assignment=assignment,
                            checkpoint_manifest_key=checkpoint_manifest_key,
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            checkpoint_cycle_status=checkpoint_cycle_status,
                            checkpoint_cycle_failures=checkpoint_cycle_failures,
                        )
                        if status_uploaded:
                            last_checkpoint_storage_success_at = time.monotonic()
                    execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                    should_exit_loop = True
                    break

                now = time.monotonic()

                if context.heartbeat_thread is not None:
                    snapshot_method = getattr(context.heartbeat_thread, "health_snapshot", None)
                    raw_snapshot = snapshot_method() if callable(snapshot_method) else None
                    snapshot = (
                        cast(HeartbeatHealthSnapshot, raw_snapshot)
                        if isinstance(raw_snapshot, HeartbeatHealthSnapshot)
                        else None
                    )
                    degraded_since = snapshot.degraded_since if snapshot is not None else None
                    is_degraded = bool(snapshot.is_degraded) if snapshot is not None else False
                    if is_degraded and isinstance(degraded_since, int | float):
                        outage_duration_seconds = max(0.0, now - float(degraded_since))
                        checkpoint_report_age_seconds = (
                            None
                            if last_checkpoint_storage_success_at is None
                            else max(0.0, now - last_checkpoint_storage_success_at)
                        )
                        checkpoint_healthy = (
                            checkpoint_report_age_seconds is not None
                            and checkpoint_report_age_seconds <= checkpoint_health_threshold_seconds
                        )
                        if not degraded_mode_active:
                            degraded_mode_active = True
                            degraded_mode_grace_logged = False
                            job_log.warning(
                                "heartbeat_degraded_mode_entered",
                                outage_duration_seconds=outage_duration_seconds,
                                grace_limit_seconds=heartbeat_grace_seconds,
                                checkpoint_report_age_seconds=checkpoint_report_age_seconds,
                                checkpoint_health_threshold_seconds=checkpoint_health_threshold_seconds,
                                consecutive_failures=getattr(snapshot, "consecutive_failures", 0),
                            )
                        if checkpoint_healthy and not degraded_mode_grace_logged:
                            degraded_mode_grace_logged = True
                            job_log.info(
                                "heartbeat_degraded_mode_grace_extended_by_checkpoint_health",
                                outage_duration_seconds=outage_duration_seconds,
                                grace_limit_seconds=heartbeat_grace_seconds,
                                checkpoint_report_age_seconds=checkpoint_report_age_seconds,
                                checkpoint_health_threshold_seconds=checkpoint_health_threshold_seconds,
                            )
                        if (
                            outage_duration_seconds > heartbeat_grace_seconds
                            and not checkpoint_healthy
                        ):
                            job_log.warning(
                                "heartbeat_degraded_mode_shutdown_triggered",
                                outage_duration_seconds=outage_duration_seconds,
                                grace_limit_seconds=heartbeat_grace_seconds,
                                checkpoint_report_age_seconds=checkpoint_report_age_seconds,
                                checkpoint_health_threshold_seconds=checkpoint_health_threshold_seconds,
                            )
                            execution.request_terminate()
                            checkpoint_manifest, manifest_uploaded = (
                                _sync_checkpoint_manifest_cycle(
                                    context=context,
                                    logger=job_log,
                                    job_id=assignment.job_id,
                                    bundle_root=bundle_root,
                                    workdir=workdir,
                                    watch_paths=_effective_checkpoint_watch_paths(execution_config),
                                    manifest=checkpoint_manifest,
                                )
                            )
                            if manifest_uploaded:
                                checkpoint_cycle_status, checkpoint_cycle_failures = (
                                    _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                                )
                                status_uploaded = _upload_checkpoint_status(
                                    context=context,
                                    assignment=assignment,
                                    workdir=workdir,
                                    checkpoint_manifest_key=checkpoint_manifest_key,
                                    checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                                    progress=latest_progress,
                                    progress_codes=latest_progress_codes,
                                    checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                                )
                                _report_checkpoint_best_effort(
                                    context=context,
                                    assignment=assignment,
                                    checkpoint_manifest_key=checkpoint_manifest_key,
                                    progress=latest_progress,
                                    progress_codes=latest_progress_codes,
                                    checkpoint_cycle_status=checkpoint_cycle_status,
                                    checkpoint_cycle_failures=checkpoint_cycle_failures,
                                )
                                if status_uploaded:
                                    last_checkpoint_storage_success_at = time.monotonic()
                            execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                            should_exit_loop = True
                            break
                    elif degraded_mode_active and snapshot is not None:
                        degraded_mode_active = False
                        degraded_mode_grace_logged = False
                        heartbeat_recovered_age_seconds = (
                            None
                            if snapshot.last_success_at is None
                            else max(0.0, now - snapshot.last_success_at)
                        )
                        job_log.info(
                            "heartbeat_degraded_mode_recovered",
                            outage_duration_seconds=0.0,
                            grace_limit_seconds=heartbeat_grace_seconds,
                            checkpoint_report_age_seconds=(
                                None
                                if last_checkpoint_storage_success_at is None
                                else max(0.0, now - last_checkpoint_storage_success_at)
                            ),
                            heartbeat_recovered_age_seconds=heartbeat_recovered_age_seconds,
                        )

                if now >= next_checkpoint_poll_time:
                    if resume_progress_baseline is not None and latest_progress < (
                        resume_progress_baseline - PROGRESS_ROLLBACK_TOLERANCE
                    ):
                        execution.request_terminate()
                        _fail_assigned_job(
                            context=context,
                            logger=job_log,
                            assignment=assignment,
                            bundle_root=bundle_root,
                            workdir=workdir,
                            execution_config=execution_config,
                            reason="excessive_progress_rollback",
                            detail=(
                                f"baseline={resume_progress_baseline}, "
                                f"latest={latest_progress}, tolerance={PROGRESS_ROLLBACK_TOLERANCE}"
                            ),
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            resume_progress_baseline=resume_progress_baseline,
                            checkpoint_manifest_path=checkpoint_manifest_path,
                        )
                        should_exit_loop = True
                        break
                    now_epoch_seconds = time.time()
                    if (
                        handoff_trigger_time is not None
                        and handoff_deadline is not None
                        and now_epoch_seconds >= handoff_trigger_time
                    ):
                        context.gateway.start_handoff(
                            job_id=assignment.job_id,
                            reason="allocation_deadline",
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            deadline_epoch_seconds=handoff_deadline,
                        )
                        execution.request_terminate()
                        execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                        checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                            context=context,
                            logger=job_log,
                            job_id=assignment.job_id,
                            bundle_root=bundle_root,
                            workdir=workdir,
                            watch_paths=_effective_checkpoint_watch_paths(execution_config),
                            manifest=checkpoint_manifest,
                        )
                        checkpoint_cycle_status: str | None = None
                        checkpoint_cycle_failures: list[dict[str, str]] = []
                        if manifest_uploaded:
                            checkpoint_cycle_status, checkpoint_cycle_failures = (
                                _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                            )
                            _upload_checkpoint_status(
                                context=context,
                                assignment=assignment,
                                workdir=workdir,
                                checkpoint_manifest_key=checkpoint_manifest_key,
                                checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                                progress=latest_progress,
                                progress_codes=latest_progress_codes,
                                checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                            )
                        context.gateway.complete_handoff(
                            job_id=assignment.job_id,
                            checkpoint_manifest_path=(
                                checkpoint_manifest_key if manifest_uploaded else None
                            ),
                            checkpoint_path=(
                                checkpoint_manifest_key if manifest_uploaded else None
                            ),
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            checkpoint_cycle_status=checkpoint_cycle_status,
                            checkpoint_cycle_failures=checkpoint_cycle_failures,
                        )
                        handoff_completed = True
                        should_exit_loop = True
                        break
                    cancellation_requested = False
                    is_cancellation_requested = getattr(
                        context.gateway, "is_cancellation_requested", None
                    )
                    if callable(is_cancellation_requested):
                        try:
                            raw_cancellation_requested = is_cancellation_requested(
                                job_id=assignment.job_id
                            )
                            if isinstance(raw_cancellation_requested, bool):
                                cancellation_requested = raw_cancellation_requested
                        except Exception:
                            cancellation_requested = False
                    if cancellation_requested:
                        job_log.info("job_cancellation_requested_by_control_plane")
                        request_terminate = getattr(execution, "request_terminate", None)
                        if callable(request_terminate):
                            request_terminate()
                            execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                            if execution.is_running():
                                execution.kill()
                                execution.wait(timeout_seconds=5)
                        checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                            context=context,
                            logger=job_log,
                            job_id=assignment.job_id,
                            bundle_root=bundle_root,
                            workdir=workdir,
                            watch_paths=_effective_checkpoint_watch_paths(execution_config),
                            manifest=checkpoint_manifest,
                        )
                        if manifest_uploaded:
                            checkpoint_cycle_status, checkpoint_cycle_failures = (
                                _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                            )
                            _upload_checkpoint_status(
                                context=context,
                                assignment=assignment,
                                workdir=workdir,
                                checkpoint_manifest_key=checkpoint_manifest_key,
                                checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                                progress=latest_progress,
                                progress_codes=latest_progress_codes,
                                checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                            )
                            _report_checkpoint_best_effort(
                                context=context,
                                assignment=assignment,
                                checkpoint_manifest_key=checkpoint_manifest_key,
                                progress=latest_progress,
                                progress_codes=latest_progress_codes,
                                checkpoint_cycle_status=checkpoint_cycle_status,
                                checkpoint_cycle_failures=checkpoint_cycle_failures,
                            )
                        should_exit_loop = True
                        break
                    checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                        context=context,
                        logger=job_log,
                        job_id=assignment.job_id,
                        bundle_root=bundle_root,
                        workdir=workdir,
                        watch_paths=_effective_checkpoint_watch_paths(execution_config),
                        manifest=checkpoint_manifest,
                    )
                    if manifest_uploaded:
                        checkpoint_cycle_status, checkpoint_cycle_failures = (
                            _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                        )
                        status_uploaded = _upload_checkpoint_status(
                            context=context,
                            assignment=assignment,
                            workdir=workdir,
                            checkpoint_manifest_key=checkpoint_manifest_key,
                            checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                        )
                        _report_checkpoint_best_effort(
                            context=context,
                            assignment=assignment,
                            checkpoint_manifest_key=checkpoint_manifest_key,
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            checkpoint_cycle_status=checkpoint_cycle_status,
                            checkpoint_cycle_failures=checkpoint_cycle_failures,
                        )
                        if status_uploaded:
                            last_checkpoint_storage_success_at = time.monotonic()
                    if checkpoint_poll_interval_seconds > 0:
                        next_checkpoint_poll_time = now + checkpoint_poll_interval_seconds
                    else:
                        next_checkpoint_poll_time = now

                supervision_failure_method = getattr(execution, "supervision_failure", None)
                if supervision_failure_method is not None:
                    supervision_failure = supervision_failure_method(now=now)
                    if supervision_failure is not None:
                        job_log.warning(
                            "job_supervision_failed",
                            reason=supervision_failure.reason,
                            detail=supervision_failure.detail,
                        )
                        execution.request_terminate()
                        if (
                            execution.wait(
                                timeout_seconds=context.sigterm_process_wait_seconds,
                            )
                            is None
                        ):
                            job_log.warning(
                                "job_supervision_killing_process",
                                reason=supervision_failure.reason,
                            )
                            execution.kill()
                            execution.wait(timeout_seconds=5)

                        if supervision_failure.reason == "fatal_log_match":
                            _ = _fatal_log_artifact(bundle_root, execution_config)
                        checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                            context=context,
                            logger=job_log,
                            job_id=assignment.job_id,
                            bundle_root=bundle_root,
                            workdir=workdir,
                            watch_paths=_effective_checkpoint_watch_paths(execution_config),
                            manifest=checkpoint_manifest,
                        )
                        if manifest_uploaded:
                            checkpoint_cycle_status, checkpoint_cycle_failures = (
                                _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                            )
                            status_uploaded = _upload_checkpoint_status(
                                context=context,
                                assignment=assignment,
                                workdir=workdir,
                                checkpoint_manifest_key=checkpoint_manifest_key,
                                checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                                progress=latest_progress,
                                progress_codes=latest_progress_codes,
                                checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                            )
                            _report_checkpoint_best_effort(
                                context=context,
                                assignment=assignment,
                                checkpoint_manifest_key=checkpoint_manifest_key,
                                progress=latest_progress,
                                progress_codes=latest_progress_codes,
                                checkpoint_cycle_status=checkpoint_cycle_status,
                                checkpoint_cycle_failures=checkpoint_cycle_failures,
                            )
                            if status_uploaded:
                                last_checkpoint_storage_success_at = time.monotonic()
                        _fail_assigned_job(
                            context=context,
                            logger=job_log,
                            assignment=assignment,
                            bundle_root=bundle_root,
                            workdir=workdir,
                            execution_config=execution_config,
                            reason=supervision_failure.reason,
                            detail=supervision_failure.detail,
                            progress=latest_progress,
                            progress_codes=latest_progress_codes,
                            resume_progress_baseline=resume_progress_baseline,
                            checkpoint_manifest_path=checkpoint_manifest_path,
                        )
                        should_exit_loop = True
                        break

                process_exit = execution.poll_exit_code()
                if process_exit is not None:
                    break

                if checkpoint_poll_interval_seconds <= 0:
                    wait_timeout = 0.0
                else:
                    until_next_checkpoint_poll = max(0.0, next_checkpoint_poll_time - now)
                    wait_timeout = min(
                        PROCESS_EXIT_POLL_INTERVAL_SECONDS,
                        until_next_checkpoint_poll,
                    )
                context.shutdown_event.wait(timeout=wait_timeout)

            if should_exit_loop:
                return handoff_completed

            checkpoint_manifest, manifest_uploaded = _sync_checkpoint_manifest_cycle(
                context=context,
                logger=job_log,
                job_id=assignment.job_id,
                bundle_root=bundle_root,
                workdir=workdir,
                watch_paths=_effective_checkpoint_watch_paths(execution_config),
                manifest=checkpoint_manifest,
            )
            if manifest_uploaded:
                checkpoint_cycle_status, checkpoint_cycle_failures = (
                    _checkpoint_diagnostics_from_manifest(checkpoint_manifest)
                )
                _upload_checkpoint_status(
                    context=context,
                    assignment=assignment,
                    workdir=workdir,
                    checkpoint_manifest_key=checkpoint_manifest_key,
                    checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
                    progress=latest_progress,
                    progress_codes=latest_progress_codes,
                    checkpoint_cycle_status=checkpoint_cycle_status or "unknown",
                )
                _report_checkpoint_best_effort(
                    context=context,
                    assignment=assignment,
                    checkpoint_manifest_key=checkpoint_manifest_key,
                    progress=latest_progress,
                    progress_codes=latest_progress_codes,
                    checkpoint_cycle_status=checkpoint_cycle_status,
                    checkpoint_cycle_failures=checkpoint_cycle_failures,
                )

            result = execution.result()
            if result.status == "completed":
                context.gateway.complete_job(job_id=assignment.job_id)
            elif result.status == "failed":
                _fail_assigned_job(
                    context=context,
                    logger=job_log,
                    assignment=assignment,
                    bundle_root=bundle_root,
                    workdir=workdir,
                    execution_config=execution_config,
                    reason="payload_failed",
                    detail=None,
                    progress=latest_progress,
                    progress_codes=latest_progress_codes,
                    resume_progress_baseline=resume_progress_baseline,
                    checkpoint_manifest_path=checkpoint_manifest_path,
                )
            return False
        finally:
            if context.heartbeat_thread is not None:
                context.heartbeat_thread.set_job_progress(
                    job_id=None,
                    progress=None,
                    progress_codes=[],
                )
            if execution.is_running():
                job_log.warning("job_execution_cleanup_terminating_process")
                execution.request_terminate()
                if execution.wait(timeout_seconds=context.sigterm_process_wait_seconds) is None:
                    job_log.warning("job_execution_cleanup_killing_process")
                    execution.kill()
                    execution.wait(timeout_seconds=5)
    return False


def run_worker(config: WorkerConfig) -> None:
    import sys

    runtime_settings = WorkerRuntimeSettings()
    if not runtime_settings.axiom_token.strip():
        LOG.error(
            "axiom_token_missing",
            message=(
                "AXIOM_TOKEN is required but not set. "
                "Set it via AXIOM_TOKEN env var or ensure Infisical is reachable during bootstrap."
            ),
        )
        sys.exit(1)
    storage = _build_storage_client(config, runtime_settings)
    orchestrator_url = config.relaymd_orchestrator_url.rstrip("/")

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    openmm_platforms = detect_openmm_platforms()
    LOG.info(
        "openmm_preflight_platforms_detected",
        openmm_platforms=openmm_platforms,
        openmm_cuda_available="CUDA" in openmm_platforms,
    )
    platform_raw = runtime_settings.worker_platform
    try:
        platform = Platform(platform_raw)
    except ValueError:
        platform = Platform.salad

    shutdown_event = threading.Event()
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

    def _sigterm_handler(signum: int, frame: FrameType | None) -> None:
        _ = (signum, frame)
        LOG.info("sigterm_received_requesting_shutdown")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _sigterm_handler)

    worker_id: UUID | None = None
    heartbeat_thread: HeartbeatThread | None = None

    try:
        LOG.info(
            "register_worker_target_resolved",
            orchestrator_url=orchestrator_url,
            register_endpoint=f"{orchestrator_url}/workers/register",
            timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
            max_attempts=runtime_settings.orchestrator_register_max_attempts,
        )
        with ApiOrchestratorGateway(
            orchestrator_url=orchestrator_url,
            api_token=config.relaymd_api_token,
            logger=LOG,
            timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
            register_worker_max_attempts=runtime_settings.orchestrator_register_max_attempts,
        ) as gateway:
            provider_id = None
            if platform == Platform.hpc:
                cluster_name = os.environ.get("RELAYMD_CLUSTER_NAME")
                slurm_job_id = os.environ.get("SLURM_JOB_ID")
                if cluster_name and slurm_job_id:
                    provider_id = f"{cluster_name}:{slurm_job_id}"

            worker_id = gateway.register_worker(
                platform=ApiPlatform(platform.value),
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
                provider_id=provider_id,
                worker_image_key=runtime_settings.worker_image_key,
            )
            worker_log = LOG.bind(worker_id=str(worker_id))

            heartbeat_thread = HeartbeatThread(
                orchestrator_url=orchestrator_url,
                worker_id=worker_id,
                api_token=config.relaymd_api_token,
                interval_seconds=runtime_settings.heartbeat_interval_seconds,
                timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
                stop_event=shutdown_event,
            )
            heartbeat_thread.start()

            context = WorkerContext(
                gateway=gateway,
                storage=storage,
                shutdown_event=shutdown_event,
                checkpoint_poll_interval_seconds=runtime_settings.checkpoint_poll_interval_seconds,
                sigterm_checkpoint_wait_seconds=runtime_settings.sigterm_checkpoint_wait_seconds,
                sigterm_checkpoint_poll_seconds=runtime_settings.sigterm_checkpoint_poll_seconds,
                sigterm_process_wait_seconds=runtime_settings.sigterm_process_wait_seconds,
                logger=worker_log,
                worker_id=worker_id,
                provider_id=provider_id,
                openmm_platforms=openmm_platforms,
                heartbeat_interval_seconds=runtime_settings.heartbeat_interval_seconds,
                heartbeat_failure_grace_multiplier=getattr(
                    runtime_settings,
                    "heartbeat_failure_grace_multiplier",
                    15,
                ),
                heartbeat_failure_grace_floor_seconds=getattr(
                    runtime_settings,
                    "heartbeat_failure_grace_floor_seconds",
                    900,
                ),
                heartbeat_thread=heartbeat_thread,
            )

            idle_start_time: float | None = None

            while not shutdown_event.is_set():
                request_response = gateway.request_job(worker_id=worker_id)
                if isinstance(request_response, ApiNoJobAvailable):
                    if runtime_settings.idle_strategy == "immediate_exit":
                        worker_log.info("no_job_available_worker_exit")
                        break

                    if idle_start_time is None:
                        idle_start_time = time.monotonic()
                        worker_log.info("entering_idle_poll")

                    if time.monotonic() - idle_start_time >= runtime_settings.idle_poll_max_seconds:
                        worker_log.info("idle_timeout_reached")
                        break

                    shutdown_event.wait(timeout=runtime_settings.idle_poll_interval_seconds)
                    continue

                if idle_start_time is not None:
                    worker_log.info("job_found_during_poll")
                    idle_start_time = None

                handoff_exit = _run_assigned_job(context=context, assignment=request_response)
                if handoff_exit:
                    worker_log.info("planned_handoff_exit")
                    break

            shutdown_event.set()
            if worker_id is not None:
                gateway.deregister_worker(worker_id=worker_id)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        shutdown_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=5)
