from __future__ import annotations

from relaymd.cli.commands.jobs import _render_jobs_plain_lines, _render_jobs_table
from relaymd.cli.commands.workers import _render_workers_table


def test_render_jobs_table_row_count() -> None:
    jobs = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "job-one",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00Z",
            "assigned_worker_id": None,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "title": "job-two",
            "status": "completed",
            "created_at": "2026-01-01T01:00:00Z",
            "assigned_worker_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
    ]

    table = _render_jobs_table(jobs)

    assert len(table.rows) == 2


def test_render_workers_table_row_count() -> None:
    workers = [
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "platform": "linux",
            "gpu_model": "A100",
            "vram_gb": 80,
            "last_heartbeat": "2026-01-01T00:00:00Z",
            "jobs_completed": 4,
            "status": "idle",
        },
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "platform": "linux",
            "gpu_model": "H100",
            "vram_gb": 96,
            "last_heartbeat": "2026-01-01T00:00:10Z",
            "jobs_completed": 9,
            "status": "busy",
        },
    ]

    table = _render_workers_table(workers)

    assert len(table.rows) == 2


def test_render_workers_table_preserves_zero_values() -> None:
    workers = [
        {
            "id": None,
            "platform": "hpc",
            "gpu_model": "A10",
            "vram_gb": 0,
            "last_heartbeat": None,
            "jobs_completed": 0,
            "status": "idle",
        }
    ]

    table = _render_workers_table(workers)

    assert table.columns[0]._cells[0] == "-"
    assert table.columns[3]._cells[0] == "0"
    assert table.columns[5]._cells[0] == "0"


def test_render_jobs_table_uses_hyphen_for_missing_ids() -> None:
    jobs = [
        {
            "id": None,
            "title": "job-one",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00Z",
            "assigned_worker_id": None,
        }
    ]

    table = _render_jobs_table(jobs)

    assert table.columns[0]._cells[0] == "-"
    assert table.columns[4]._cells[0] == "-"


def test_render_jobs_plain_lines_tsv_output() -> None:
    jobs = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "job-one",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00Z",
            "assigned_worker_id": None,
        }
    ]

    lines = _render_jobs_plain_lines(jobs)

    assert lines[0] == "id\ttitle\tstatus\tcreated_at\tassigned_worker_id"
    assert (
        lines[1]
        == "11111111-1111-1111-1111-111111111111\tjob-one\tqueued\t2026-01-01T00:00:00Z\t-"
    )
