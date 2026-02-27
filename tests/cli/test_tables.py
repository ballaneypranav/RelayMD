from __future__ import annotations

from relaymd.cli.commands.jobs import _render_jobs_plain_lines
from relaymd.cli.commands.workers import _render_workers_plain_lines


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


def test_render_workers_plain_lines_tsv_output() -> None:
    workers = [
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "platform": "linux",
            "gpu_model": "A100",
            "vram_gb": 80,
            "last_heartbeat": "2026-01-01T00:00:00Z",
            "jobs_completed": 4,
            "status": "idle",
        }
    ]

    lines = _render_workers_plain_lines(workers)

    assert lines[0] == "id\tplatform\tgpu_model\tvram_gb\tlast_heartbeat\tjobs_completed\tstatus"
    assert (
        lines[1]
        == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\tlinux\tA100\t80\t2026-01-01T00:00:00Z\t4\tidle"
    )


def test_render_workers_plain_lines_preserves_zero_values() -> None:
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

    lines = _render_workers_plain_lines(workers)

    assert lines[1] == "-\thpc\tA10\t0\t-\t0\tidle"
