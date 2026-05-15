from __future__ import annotations

from datetime import UTC, datetime

from relaymd.cli.commands.jobs_export import job_to_export_row, parse_timestamp


def test_parse_timestamp_accepts_negative_timezone_offset() -> None:
    parsed = parse_timestamp("2026-05-05T13:23:03-05:00")
    assert parsed is not None
    assert parsed.isoformat() == "2026-05-05T18:23:03+00:00"


def test_export_row_handles_non_numeric_progress_without_crashing() -> None:
    now = datetime(2026, 5, 15, tzinfo=UTC)
    row = job_to_export_row(
        {
            "id": "job-1",
            "title": "test",
            "status": "running",
            "assigned_at": "2026-05-15T00:00:00Z",
            "progress": "not-a-number",
            "created_at": "2026-05-15T00:00:00Z",
        },
        now,
    )
    assert row["progress"] == "0.0%"
    assert row["progress_percent"] == "0.0%"
    assert row["etc_seconds"] == "-"


def test_export_row_renders_iso_fields_in_eastern_time() -> None:
    now = datetime(2026, 5, 15, tzinfo=UTC)
    row = job_to_export_row(
        {
            "id": "job-1",
            "title": "test",
            "status": "running",
            "created_at": "2026-05-15T12:00:00Z",
            "assigned_at": "2026-01-15T12:00:00Z",
            "started_at": "2026-05-15T13:00:00Z",
            "status_changed_at": "2026-05-15T13:30:00Z",
            "updated_at": "2026-05-15T14:00:00Z",
        },
        now,
    )
    assert row["created_at_iso"] == "2026-05-15T08:00:00-04:00 EDT"
    assert row["assigned_at_iso"] == "2026-01-15T07:00:00-05:00 EST"
    assert row["started_at_iso"] == "2026-05-15T09:00:00-04:00 EDT"
    assert row["status_changed_at_iso"] == "2026-05-15T09:30:00-04:00 EDT"
    assert row["updated_at_iso"] == "2026-05-15T10:00:00-04:00 EDT"
