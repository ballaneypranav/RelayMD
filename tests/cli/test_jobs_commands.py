from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from relaymd_api_client.models.job_read import JobRead
from relaymd_api_client.models.job_status import JobStatus

from relaymd.cli.commands.jobs import JOB_EXPORT_COLUMNS, export_jobs_csv, prune_jobs
from relaymd.cli.commands.jobs_checkpoint import (
    download_all_checkpoints,
    download_checkpoint_file,
)


def _make_job_read(
    title: str = "test",
    status: JobStatus | None = None,
    updated_days_ago: int = 60,
) -> JobRead:
    if status is None:
        status = JobStatus("completed")
    updated = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=updated_days_ago)
    return JobRead.from_dict(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "title": title,
            "status": status.value,
            "input_bundle_path": "x",
            "assigned_at": None,
            "started_at": None,
            "status_changed_at": updated.isoformat(),
            "latest_checkpoint_manifest_path": None,
            "latest_failure_artifact_path": None,
            "last_checkpoint_at": None,
            "assigned_worker_id": None,
            "created_at": updated.isoformat(),
            "updated_at": updated.isoformat(),
            "slurm_job_id": None,
        }
    )


def test_prune_jobs_calls_service_with_correct_args(capsys) -> None:
    mock_service = MagicMock()
    mock_service.prune_jobs.return_value = 5

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
    ):
        prune_jobs(
            statuses=["completed", "failed"],
            older_than=14,
            dry_run=False,
            json_mode=False,
        )

    mock_service.prune_jobs.assert_called_once_with(
        statuses=["completed", "failed"], older_than_days=14
    )
    captured = capsys.readouterr()
    assert "5" in captured.out
    assert "14" in captured.out


def test_prune_jobs_json_output(capsys) -> None:
    mock_service = MagicMock()
    mock_service.prune_jobs.return_value = 3

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
    ):
        prune_jobs(
            statuses=["completed"],
            older_than=30,
            dry_run=False,
            json_mode=True,
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {"deleted": 3}


def test_prune_jobs_dry_run_counts_without_deleting(capsys) -> None:
    old_job = _make_job_read(status=JobStatus("completed"), updated_days_ago=60)
    recent_job = _make_job_read(status=JobStatus("completed"), updated_days_ago=1)
    active_job = _make_job_read(status=JobStatus("queued"), updated_days_ago=60)

    mock_service = MagicMock()
    mock_service.list_jobs.return_value = [old_job, recent_job, active_job]

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
    ):
        prune_jobs(
            statuses=["completed", "failed", "cancelled"],
            older_than=30,
            dry_run=True,
            json_mode=False,
        )

    mock_service.prune_jobs.assert_not_called()
    captured = capsys.readouterr()
    assert "1" in captured.out


def test_prune_jobs_dry_run_json(capsys) -> None:
    old_job = _make_job_read(status=JobStatus("failed"), updated_days_ago=45)
    mock_service = MagicMock()
    mock_service.list_jobs.return_value = [old_job]

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
    ):
        prune_jobs(
            statuses=["completed", "failed", "cancelled"],
            older_than=30,
            dry_run=True,
            json_mode=True,
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["dry_run"] is True
    assert payload["would_delete"] == 1


def test_prune_jobs_rejects_invalid_status() -> None:
    with pytest.raises(typer.Exit) as exc:
        prune_jobs(
            statuses=["running"],
            older_than=30,
            dry_run=False,
            json_mode=False,
        )
    assert exc.value.exit_code == 1


def test_prune_jobs_service_error_exits_nonzero() -> None:
    mock_service = MagicMock()
    mock_service.prune_jobs.side_effect = RuntimeError("connection refused")

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
        pytest.raises(typer.Exit) as exc,
    ):
        prune_jobs(
            statuses=["completed"],
            older_than=30,
            dry_run=False,
            json_mode=False,
        )
    assert exc.value.exit_code == 1


def test_download_checkpoint_file_json_output(capsys) -> None:
    mock_service = MagicMock()
    mock_service.download_checkpoint_file.return_value = {
        "job_id": "j1",
        "relative_path": "state/a.chk",
        "remote_key": "jobs/j1/checkpoints/files/state/a.chk",
        "local_path": "/tmp/a.chk",
        "bytes": 7,
    }

    with (
        patch("relaymd.cli.commands.jobs_checkpoint.create_cli_context"),
        patch("relaymd.cli.commands.jobs_checkpoint.JobsService", return_value=mock_service),
    ):
        download_checkpoint_file(
            job_id="00000000-0000-0000-0000-000000000001",
            relative_path="state/a.chk",
            output=None,
            json_mode=True,
        )

    payload = json.loads(capsys.readouterr().out)
    assert payload["relative_path"] == "state/a.chk"
    assert payload["bytes"] == 7


def test_download_all_checkpoints_partial_failure_exits_nonzero(capsys) -> None:
    mock_service = MagicMock()
    mock_service.download_all_checkpoint_files.return_value = {
        "job_id": "j1",
        "manifest_path": "/tmp/out/manifest.json",
        "output_dir": "/tmp/out",
        "status": "partial_failure",
        "downloaded_files": 1,
        "failed_files": 1,
        "total_files": 2,
        "total_bytes": 10,
        "results": [],
    }

    with (
        patch("relaymd.cli.commands.jobs_checkpoint.create_cli_context"),
        patch("relaymd.cli.commands.jobs_checkpoint.JobsService", return_value=mock_service),
        pytest.raises(typer.Exit) as exc,
    ):
        download_all_checkpoints(
            job_id="00000000-0000-0000-0000-000000000001",
            output_dir=None,
            json_mode=True,
        )

    assert exc.value.exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "partial_failure"


def test_export_jobs_csv_writes_default_columns(tmp_path) -> None:
    mock_service = MagicMock()
    mock_service.list_jobs.return_value = [_make_job_read()]
    output = tmp_path / "jobs.csv"

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
    ):
        export_jobs_csv(output=output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines
    assert lines[0] == ",".join(JOB_EXPORT_COLUMNS)
    assert "00000000-0000-0000-0000-000000000001" in lines[1]


def test_cli_export_columns_match_frontend_export_columns() -> None:
    jobs_view = Path("frontend/src/views/JobsView.tsx").read_text(encoding="utf-8")
    marker = "export const JOB_EXPORT_COLUMN_KEYS"
    start = jobs_view.find(marker)
    assert start != -1
    list_start = jobs_view.find("[", start)
    list_end = jobs_view.find("];", list_start)
    assert list_start != -1 and list_end != -1
    list_text = jobs_view[list_start + 1 : list_end]
    frontend_columns = re.findall(r'"([^"]+)"', list_text)
    assert frontend_columns == JOB_EXPORT_COLUMNS


def test_export_jobs_csv_exits_nonzero_on_list_error() -> None:
    mock_service = MagicMock()
    mock_service.list_jobs.side_effect = RuntimeError("boom")

    with (
        patch("relaymd.cli.commands.jobs.create_cli_context"),
        patch("relaymd.cli.commands.jobs.JobsService", return_value=mock_service),
        pytest.raises(typer.Exit) as exc,
    ):
        export_jobs_csv()

    assert exc.value.exit_code == 1
