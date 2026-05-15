from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from relaymd.cli.services.jobs_service import JobsService
from tests.cli._services_test_helpers import (
    _as_cli_context,
    _FakeContext,
    _make_checkpoint_job_read,
)

EXPECTED_TOTAL_FILES = 2


def test_jobs_service_download_checkpoint_file_success(tmp_path: Path, monkeypatch) -> None:
    context = _FakeContext()
    service = JobsService(_as_cli_context(context))
    job = _make_checkpoint_job_read()
    monkeypatch.setattr(service, "get_job", Mock(return_value=job))

    manifest = {
        "files": {
            "state/checkpoint.chk": {
                "remote_key": "jobs/abc/checkpoints/files/state/checkpoint.chk"
            }
        }
    }

    def _download(key: str, path: Path) -> None:
        if key.endswith("manifest.json"):
            path.write_text(json.dumps(manifest), encoding="utf-8")
        else:
            path.write_bytes(b"checkpoint-bytes")

    context.storage.download_file.side_effect = _download

    payload = service.download_checkpoint_file(
        job_id=job.id,
        relative_path="state/checkpoint.chk",
        output=tmp_path,
    )

    assert payload["remote_key"] == "jobs/abc/checkpoints/files/state/checkpoint.chk"
    assert Path(str(payload["local_path"])).read_bytes() == b"checkpoint-bytes"


def test_jobs_service_download_all_checkpoint_files_partial_failure(
    tmp_path: Path, monkeypatch
) -> None:
    context = _FakeContext()
    service = JobsService(_as_cli_context(context))
    job = _make_checkpoint_job_read()
    monkeypatch.setattr(service, "get_job", Mock(return_value=job))

    manifest = {
        "files": {
            "a.chk": {"remote_key": "jobs/abc/checkpoints/files/a.chk"},
            "b.chk": {"remote_key": "jobs/abc/checkpoints/files/b.chk"},
        }
    }

    def _download(key: str, path: Path) -> None:
        if key.endswith("manifest.json"):
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return
        if key.endswith("/a.chk"):
            path.write_bytes(b"a")
            return
        raise RuntimeError("download exploded")

    context.storage.download_file.side_effect = _download
    payload = service.download_all_checkpoint_files(job_id=job.id, output_dir=tmp_path)

    assert payload["status"] == "partial_failure"
    assert payload["downloaded_files"] == 1
    assert payload["failed_files"] == 1
    assert payload["total_files"] == EXPECTED_TOTAL_FILES


def test_jobs_service_download_all_checkpoint_files_rejects_traversal_paths(
    tmp_path: Path, monkeypatch
) -> None:
    context = _FakeContext()
    service = JobsService(_as_cli_context(context))
    job = _make_checkpoint_job_read()
    monkeypatch.setattr(service, "get_job", Mock(return_value=job))

    manifest = {
        "files": {
            "../escape.chk": {"remote_key": "jobs/abc/checkpoints/files/escape.chk"},
            "good.chk": {"remote_key": "jobs/abc/checkpoints/files/good.chk"},
        }
    }

    def _download(key: str, path: Path) -> None:
        if key.endswith("manifest.json"):
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return
        path.write_bytes(b"ok")

    context.storage.download_file.side_effect = _download
    payload = service.download_all_checkpoint_files(job_id=job.id, output_dir=tmp_path)

    assert payload["status"] == "partial_failure"
    assert payload["downloaded_files"] == 1
    assert payload["failed_files"] == 1
    assert payload["total_files"] == EXPECTED_TOTAL_FILES
    results = payload["results"]
    assert isinstance(results, list)
    assert any(
        isinstance(result, dict) and result.get("relative_path") == "../escape.chk"
        for result in results
    )
    assert not (tmp_path.parent / "escape.chk").exists()


def test_jobs_service_download_all_checkpoint_files_includes_preserved_output(
    tmp_path: Path, monkeypatch
) -> None:
    context = _FakeContext()
    service = JobsService(_as_cli_context(context))
    job = _make_checkpoint_job_read()
    monkeypatch.setattr(service, "get_job", Mock(return_value=job))

    manifest = {
        "files": {"a.chk": {"remote_key": "jobs/abc/checkpoints/files/a.chk"}},
        "preserved_outputs": {
            "r0/FOL_APT.out": {
                "snapshots": [
                    {
                        "resume_segment": 1,
                        "remote_key": "jobs/abc/checkpoints/preserved-output/r0/FOL_APT.out/0001",
                    }
                ]
            }
        },
    }

    def _download(key: str, path: Path) -> None:
        if key.endswith("manifest.json"):
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return
        path.write_bytes(key.encode("utf-8"))

    context.storage.download_file.side_effect = _download
    payload = service.download_all_checkpoint_files(job_id=job.id, output_dir=tmp_path)

    assert payload["status"] == "success"
    assert payload["downloaded_files"] == EXPECTED_TOTAL_FILES
    assert payload["failed_files"] == 0
    assert payload["total_files"] == EXPECTED_TOTAL_FILES
    assert (tmp_path / "files" / "a.chk").is_file()
    assert (tmp_path / "preserved-output" / "r0" / "FOL_APT.out" / "0001" / "0001").is_file()
