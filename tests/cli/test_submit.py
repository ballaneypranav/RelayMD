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
from typer.testing import CliRunner

from relaymd.cli.commands import submit as submit_cmd


def _submit_cli_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(submit_cmd.submit)
    return app


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

    class FakeSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            uploaded["path"] = local_archive
            uploaded["key"] = b2_key
            with tarfile.open(local_archive, "r:gz") as tar:
                uploaded["tar_names"] = tar.getnames()
                worker_json = tar.extractfile("relaymd-worker.json")
                assert worker_json is not None
                uploaded["worker_config"] = json.loads(worker_json.read().decode("utf-8"))

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            assert isinstance(job_id, uuid.UUID)
            assert title == "test-job"
            assert b2_key.startswith("jobs/")
            assert b2_key.endswith("/input/bundle.tar.gz")
            created_job.id = job_id
            return created_job

    monkeypatch.setattr(submit_cmd, "SubmitService", FakeSubmitService)
    create_context = Mock(return_value=object())
    monkeypatch.setattr(submit_cmd, "create_cli_context", create_context)

    submit_cmd.submit(
        input_dir=input_dir,
        title="test-job",
        command="python run.py",
        checkpoint_glob="*.cpt",
        checkpoint_poll_interval_seconds=60,
    )

    worker_json = input_dir / "relaymd-worker.json"
    assert not worker_json.exists()
    assert uploaded["worker_config"] == {
        "command": "python run.py",
        "checkpoint_glob_pattern": "*.cpt",
        "checkpoint_poll_interval_seconds": 60,
    }
    assert "relaymd-worker.json" in uploaded["tar_names"]
    assert uploaded["key"].startswith("jobs/")
    assert uploaded["key"].endswith("/input/bundle.tar.gz")
    create_context.assert_called_once_with()


def test_submit_aborts_when_worker_config_missing_and_no_command(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "hello.txt").write_text("hello", encoding="utf-8")

    with pytest.raises(submit_cmd.SubmitCommandError) as exc:
        submit_cmd.ensure_worker_config(
            input_dir,
            command=None,
            checkpoint_glob=None,
            checkpoint_poll_interval_seconds=None,
        )

    assert exc.value.code == "missing_worker_config"


def test_submit_escapes_exception_messages_for_rich_markup(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")

    class FailingSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            _ = (local_archive, b2_key)
            raise RuntimeError("bad markup token [/:] from upstream")

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            _ = (title, b2_key)
            raise AssertionError("register_job should not be called after upload failure")

    monkeypatch.setattr(submit_cmd, "SubmitService", FailingSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))

    with pytest.raises(typer.Exit) as exc:
        submit_cmd.submit(input_dir=input_dir, title="failing-job")

    assert exc.value.exit_code == 1


def test_submit_command_requires_checkpoint_glob(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with pytest.raises(submit_cmd.SubmitCommandError) as exc:
        submit_cmd.ensure_worker_config(
            input_dir,
            command="python run.py",
            checkpoint_glob=None,
            checkpoint_poll_interval_seconds=None,
        )
    assert exc.value.code == "missing_checkpoint_glob"


def test_submit_json_invalid_input_dir_emits_json_error_only(tmp_path: Path) -> None:
    runner = CliRunner()
    missing = tmp_path / "missing-input"
    result = runner.invoke(
        _submit_cli_app(),
        [str(missing), "--title", "x", "--json"],
    )
    assert result.exit_code == 1
    assert result.stdout
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_input_dir"


def test_submit_json_missing_checkpoint_glob_emits_json_error_only(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "f.txt").write_text("x", encoding="utf-8")

    class FakeSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            _ = (local_archive, b2_key)

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            raise AssertionError("register_job should not be reached")

    monkeypatch.setattr(submit_cmd, "SubmitService", FakeSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [str(input_dir), "--title", "x", "--command", "python run.py", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "missing_checkpoint_glob"


def test_submit_json_missing_settings_emits_json_error_only(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")
    monkeypatch.setattr(
        submit_cmd,
        "create_cli_context",
        Mock(side_effect=RuntimeError("settings boom")),
    )
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [str(input_dir), "--title", "x", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "missing_settings"


def test_submit_json_local_validation_precedes_settings_load(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "f.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        submit_cmd,
        "create_cli_context",
        Mock(side_effect=RuntimeError("settings boom")),
    )
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [str(input_dir), "--title", "x", "--command", "python run.py", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "missing_checkpoint_glob"


def test_submit_json_upload_failed_emits_json_error_only(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")

    class FailingSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            _ = (local_archive, b2_key)
            raise RuntimeError("upload boom")

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            _ = (job_id, title, b2_key)
            raise AssertionError("register_job should not be reached")

    monkeypatch.setattr(submit_cmd, "SubmitService", FailingSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [str(input_dir), "--title", "x", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "upload_failed"


def test_submit_json_registration_failed_emits_json_error_only(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "relaymd-worker.json").write_text('{"command": "run"}\n', encoding="utf-8")

    class FailingSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            _ = (local_archive, b2_key)

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            _ = (job_id, title, b2_key)
            raise RuntimeError("register boom")

    monkeypatch.setattr(submit_cmd, "SubmitService", FailingSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [str(input_dir), "--title", "x", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "registration_failed"


def test_submit_json_invalid_checkpoint_poll_interval_emits_json_error_only(
    monkeypatch, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "f.txt").write_text("x", encoding="utf-8")

    class FakeSubmitService:
        def __init__(self, context) -> None:
            _ = context

        def upload_bundle(self, *, local_archive: Path, b2_key: str) -> None:
            _ = (local_archive, b2_key)

        def register_job(self, *, job_id: uuid.UUID, title: str, b2_key: str):
            raise AssertionError("register_job should not be reached")

    monkeypatch.setattr(submit_cmd, "SubmitService", FakeSubmitService)
    monkeypatch.setattr(submit_cmd, "create_cli_context", Mock(return_value=object()))
    runner = CliRunner()
    result = runner.invoke(
        _submit_cli_app(),
        [
            str(input_dir),
            "--title",
            "x",
            "--command",
            "python run.py",
            "--checkpoint-glob",
            "*.chk",
            "--checkpoint-poll-interval-seconds",
            "0",
            "--json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_checkpoint_poll_interval"
