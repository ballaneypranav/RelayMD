from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import UUID


class StorageClientProtocol(Protocol):
    def download_file(self, b2_key: str, local_path: Path) -> None: ...


def json_dumps_error(code: str, message: str) -> str:
    return f'{{"error": {{"code": "{code}", "message": "{message}"}}}}'


def validate_relative_path(value: str) -> str:
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


def parse_manifest_files(manifest: dict[str, object]) -> dict[str, object]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise RuntimeError(
            json_dumps_error(
                "manifest_invalid", "Checkpoint manifest is missing object field 'files'"
            )
        )
    return files


def parse_manifest_preserved_outputs(manifest: dict[str, object]) -> dict[str, list[object]]:
    preserved_outputs = manifest.get("preserved_outputs")
    if preserved_outputs is None:
        return {}
    if not isinstance(preserved_outputs, dict):
        raise RuntimeError(
            json_dumps_error(
                "manifest_invalid",
                "Checkpoint manifest field 'preserved_outputs' must be an object",
            )
        )

    parsed: dict[str, list[object]] = {}
    for relative_path, entry in preserved_outputs.items():
        if not isinstance(relative_path, str) or not relative_path:
            raise RuntimeError(
                json_dumps_error(
                    "manifest_invalid", "Checkpoint manifest preserved output path is invalid"
                )
            )
        if not isinstance(entry, dict):
            raise RuntimeError(
                json_dumps_error(
                    "manifest_invalid",
                    "Checkpoint manifest preserved output entry must be an object",
                )
            )
        snapshots = entry.get("snapshots")
        if snapshots is None:
            parsed[relative_path] = []
            continue
        if not isinstance(snapshots, list):
            raise RuntimeError(
                json_dumps_error(
                    "manifest_invalid",
                    "Checkpoint manifest preserved output snapshots must be an array",
                )
            )
        parsed[relative_path] = snapshots
    return parsed


def read_checkpoint_manifest(
    *,
    storage: StorageClientProtocol,
    manifest_key: str,
    output_path: Path | None = None,
) -> dict[str, object]:
    if output_path is not None:
        manifest_local_path = output_path
        manifest_local_path.parent.mkdir(parents=True, exist_ok=True)
        storage.download_file(manifest_key, manifest_local_path)
    else:
        with tempfile.TemporaryDirectory(prefix="relaymd-manifest-") as tmpdir:
            manifest_local_path = Path(tmpdir) / "manifest.json"
            storage.download_file(manifest_key, manifest_local_path)
            return _read_manifest_json(manifest_local_path)
    return _read_manifest_json(manifest_local_path)


def download_all_checkpoint_materialized(  # noqa: C901, PLR0915
    *,
    storage: StorageClientProtocol,
    job_id: UUID,
    base_output_dir: Path,
    manifest: dict[str, object],
    manifest_local_path: Path,
) -> dict[str, object]:
    files = parse_manifest_files(manifest)
    preserved_outputs = parse_manifest_preserved_outputs(manifest)

    results: list[dict[str, object]] = []
    failed_files = 0
    downloaded_files = 0
    total_bytes = 0

    for relative_path in sorted(files.keys()):
        try:
            validated_relative_path = validate_relative_path(relative_path)
        except RuntimeError as exc:
            failed_files += 1
            results.append(
                {
                    "relative_path": relative_path,
                    "remote_key": "",
                    "local_path": "",
                    "bytes": 0,
                    "error": str(exc),
                }
            )
            continue

        entry = files[relative_path]
        if not isinstance(entry, dict):
            failed_files += 1
            results.append(
                {
                    "relative_path": validated_relative_path,
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
                    "relative_path": validated_relative_path,
                    "remote_key": "",
                    "local_path": "",
                    "bytes": 0,
                    "error": "Manifest file entry has invalid remote_key",
                }
            )
            continue

        local_path = base_output_dir / "files" / validated_relative_path
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            storage.download_file(remote_key, local_path)
            file_size = local_path.stat().st_size
        except Exception as exc:  # noqa: BLE001
            failed_files += 1
            results.append(
                {
                    "relative_path": validated_relative_path,
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
                "relative_path": validated_relative_path,
                "remote_key": remote_key,
                "local_path": str(local_path),
                "bytes": file_size,
            }
        )

    for relative_path in sorted(preserved_outputs.keys()):
        snapshots = preserved_outputs[relative_path]
        for index, snapshot in enumerate(snapshots):
            if not isinstance(snapshot, dict):
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": "",
                        "local_path": "",
                        "bytes": 0,
                        "error": "Preserved output snapshot entry is not an object",
                    }
                )
                continue
            remote_key = snapshot.get("remote_key")
            resume_segment = snapshot.get("resume_segment")
            if not isinstance(remote_key, str) or not remote_key:
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": "",
                        "local_path": "",
                        "bytes": 0,
                        "error": "Preserved output snapshot has invalid remote_key",
                    }
                )
                continue
            if not isinstance(resume_segment, int) or resume_segment <= 0:
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": remote_key,
                        "local_path": "",
                        "bytes": 0,
                        "error": "Preserved output snapshot has invalid resume_segment",
                    }
                )
                continue

            try:
                validated_relative_path = validate_relative_path(relative_path)
            except RuntimeError as exc:
                failed_files += 1
                results.append(
                    {
                        "relative_path": relative_path,
                        "remote_key": remote_key,
                        "local_path": "",
                        "bytes": 0,
                        "error": str(exc),
                    }
                )
                continue
            suffix = Path(remote_key).name or f"snapshot-{index + 1}"
            local_path = (
                base_output_dir
                / "preserved-output"
                / validated_relative_path
                / f"{resume_segment:04d}"
                / suffix
            )
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                storage.download_file(remote_key, local_path)
                file_size = local_path.stat().st_size
            except Exception as exc:  # noqa: BLE001
                failed_files += 1
                results.append(
                    {
                        "relative_path": validated_relative_path,
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
                    "relative_path": validated_relative_path,
                    "remote_key": remote_key,
                    "local_path": str(local_path),
                    "bytes": file_size,
                    "resume_segment": resume_segment,
                }
            )

    return {
        "job_id": str(job_id),
        "manifest_path": str(manifest_local_path),
        "output_dir": str(base_output_dir),
        "status": "partial_failure" if failed_files > 0 else "success",
        "downloaded_files": downloaded_files,
        "failed_files": failed_files,
        "total_files": len(files) + sum(len(snapshots) for snapshots in preserved_outputs.values()),
        "total_bytes": total_bytes,
        "results": results,
    }


def _read_manifest_json(manifest_local_path: Path) -> dict[str, object]:
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
