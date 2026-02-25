from __future__ import annotations

import json
import tarfile
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer
from relaymd.cli.commands import submit as submit_cmd


class _FakeSettings:
    orchestrator_url = "http://localhost:8000"
    api_token = "token"
    b2_endpoint_url = "https://b2.example"
    b2_bucket_name = "bucket"
    b2_access_key_id = "key"
    b2_secret_access_key = "secret"


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

    class FakeBoto3Client:
        def upload_file(self, local_path: str, bucket_name: str, b2_key: str) -> None:
            uploaded["path"] = Path(local_path)
            uploaded["bucket"] = bucket_name
            uploaded["key"] = b2_key
            with tarfile.open(local_path, "r:gz") as tar:
                uploaded["tar_names"] = tar.getnames()
                worker_json = tar.extractfile("relaymd-worker.json")
                assert worker_json is not None
                uploaded["worker_config"] = json.loads(worker_json.read().decode("utf-8"))

    fake_http_client = Mock()
    fake_response = Mock()
    fake_response.json.return_value = {"id": str(uuid.uuid4())}
    fake_response.raise_for_status.return_value = None
    fake_http_client.post.return_value = fake_response
    fake_http_cm = Mock()
    fake_http_cm.__enter__ = Mock(return_value=fake_http_client)
    fake_http_cm.__exit__ = Mock(return_value=False)

    monkeypatch.setattr(submit_cmd.boto3, "client", Mock(return_value=FakeBoto3Client()))
    monkeypatch.setattr(submit_cmd.httpx, "Client", Mock(return_value=fake_http_cm))
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
