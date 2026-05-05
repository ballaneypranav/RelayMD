from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import typer
from relaymd_api_client.models.job_read import JobRead
from relaymd_api_client.models.job_status import JobStatus

from relaymd.cli.commands.jobs import prune_jobs


def _make_job_read(
    title: str = "test",
    status: JobStatus = JobStatus.COMPLETED,
    updated_days_ago: int = 60,
) -> JobRead:
    updated = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=updated_days_ago)
    return JobRead.from_dict(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "title": title,
            "status": status.value,
            "input_bundle_path": "x",
            "latest_checkpoint_path": None,
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
    old_job = _make_job_read(status=JobStatus.COMPLETED, updated_days_ago=60)
    recent_job = _make_job_read(status=JobStatus.COMPLETED, updated_days_ago=1)
    active_job = _make_job_read(status=JobStatus.QUEUED, updated_days_ago=60)

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
    old_job = _make_job_read(status=JobStatus.FAILED, updated_days_ago=45)
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
