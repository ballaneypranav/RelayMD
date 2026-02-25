from __future__ import annotations

import json
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer
from relaymd_api_client.models.job_read import JobRead

from relaymd.cli.commands import submit as submit_cmd


class _FakeSettings:
    orchestrator_url = "http://localhost:8000"
    api_token = "token"
    b2_endpoint_url = "https://b2.example"
    b2_bucket_name = "bucket"
    b2_access_key_id = "key"
    b2_secret_access_key = "secret"
    cf_worker_url = "https://cloudflare.example"
    cf_bearer_token = ""


def test_create_bundle_archive_uses_flat_archive_root(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")
    (input_dir / "input.txt").write_text("data", encoding="utf-8")
    nested = input_dir / "nested"
    nested.mkdir()
    (nested / "checkpoint.dat").write_text("cpt", encoding="utf-8")

    bundle = tmp_path / "bundle.tar.gz"
    submit_cmd.create_bundle_archive(input_dir, bundle)

    with tarfile.open(bundle, "r:gz") as tar:
        names = tar.getnames()

    assert "relaymd-worker.json" in names
    assert "input.txt" in names
    assert "nested/checkpoint.dat" in names
    assert all(not name.startswith("input/") for name in names)


def test_submit_writes_worker_json_when_command_flag_provided(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "hello.txt").write_text("hello", encoding="utf-8")

    uploaded = {}

    class FakeStorageClient:
        def __init__(
            self,
            *,
            b2_endpoint_url: str,
            b2_bucket_name: str,
            b2_access_key_id: str,
            b2_secret_access_key: str,
            cf_worker_url: str,
            cf_bearer_token: str,
        ) -> None:
            uploaded["bucket"] = b2_bucket_name
            assert b2_endpoint_url == "https://b2.example"
            assert b2_access_key_id == "key"
            assert b2_secret_access_key == "secret"
            assert cf_worker_url == "https://cloudflare.example"
            assert cf_bearer_token == ""

        def upload_file(self, local_path: Path, b2_key: str) -> None:
            uploaded["path"] = local_path
            uploaded["key"] = b2_key
            with tarfile.open(local_path, "r:gz") as tar:
                uploaded["tar_names"] = tar.getnames()
                worker_json = tar.extractfile("relaymd-worker.json")
                assert worker_json is not None
                uploaded["worker_config"] = json.loads(worker_json.read().decode("utf-8"))

    class _FakeApiClient:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type, exc, tb) -> bool:
            _ = (exc_type, exc, tb)
            return False

    created_at = datetime.now(UTC)
    created_job = JobRead.from_dict(
        {
            "id": str(uuid.uuid4()),
            "title": "test-job",
            "status": "queued",
            "input_bundle_path": "jobs/x/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
            "last_checkpoint_at": None,
            "assigned_worker_id": None,
            "created_at": created_at.isoformat(),
            "updated_at": created_at.isoformat(),
        }
    )

    def _fake_create_job_sync(*, client: object, body: object, x_api_token: str) -> JobRead:
        _ = client
        assert x_api_token == "token"
        assert getattr(body, "title", None) == "test-job"
        assert str(getattr(body, "input_bundle_path", "")).startswith("jobs/")
        return created_job

    monkeypatch.setattr(submit_cmd, "StorageClient", FakeStorageClient)
    monkeypatch.setattr(submit_cmd, "RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(submit_cmd.create_job_jobs_post, "sync", _fake_create_job_sync)
    monkeypatch.setattr(submit_cmd, "load_settings", lambda: _FakeSettings())

    submit_cmd.submit(
        input_dir=input_dir,
        title="test-job",
        command="python run.py",
        checkpoint_glob="*.cpt",
    )

    worker_json = input_dir / "relaymd-worker.json"
    assert worker_json.exists()
    worker_payload = json.loads(worker_json.read_text(encoding="utf-8"))
    assert worker_payload == {
        "command": "python run.py",
        "checkpoint_glob_pattern": "*.cpt",
    }
    assert "relaymd-worker.json" in uploaded["tar_names"]
    assert uploaded["worker_config"] == worker_payload
    assert uploaded["bucket"] == "bucket"
    assert uploaded["key"].startswith("jobs/")
    assert uploaded["key"].endswith("/input/bundle.tar.gz")


def test_submit_aborts_when_worker_config_missing_and_no_command(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "hello.txt").write_text("hello", encoding="utf-8")

    with pytest.raises(typer.Exit) as exc:
        submit_cmd.ensure_worker_config(input_dir, command=None, checkpoint_glob=None)

    assert exc.value.exit_code == 1
