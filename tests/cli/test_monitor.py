from __future__ import annotations

from relaymd.cli.commands import monitor as monitor_cmd


def test_build_monitor_snapshot_lines_includes_jobs_and_workers_sections() -> None:
    jobs = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "title": "job-one",
            "status": "queued",
            "created_at": "2026-01-01T00:00:00Z",
            "assigned_worker_id": None,
        }
    ]
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

    lines = monitor_cmd._build_monitor_snapshot_lines(
        updated_at="2026-01-01T00:00:01Z",
        jobs=jobs,
        workers=workers,
    )

    assert lines[0] == "updated_at\t2026-01-01T00:00:01Z"
    assert "[jobs]" in lines
    assert "id\ttitle\tstatus\tcreated_at\tassigned_worker_id" in lines
    assert "[workers]" in lines
    assert "id\tplatform\tgpu_model\tvram_gb\tlast_heartbeat\tjobs_completed\tstatus" in lines


def test_monitor_renders_one_iteration_and_exits_on_keyboard_interrupt(monkeypatch) -> None:
    class _FakeJob:
        def to_dict(self) -> dict[str, object]:
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "title": "job-one",
                "status": "queued",
                "created_at": "2026-01-01T00:00:00Z",
                "assigned_worker_id": None,
            }

    class _FakeWorker:
        def to_dict(self) -> dict[str, object]:
            return {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "platform": "linux",
                "gpu_model": "A100",
                "vram_gb": 80,
                "last_heartbeat": "2026-01-01T00:00:00Z",
                "jobs_completed": 4,
                "status": "idle",
            }

    class _FakeJobsService:
        def __init__(self, context) -> None:
            _ = context

        def list_jobs(self):
            return [_FakeJob()]

    class _FakeWorkersService:
        def __init__(self, context) -> None:
            _ = context

        def list_workers(self):
            return [_FakeWorker()]

    emitted: list[str] = []
    monkeypatch.setattr(monitor_cmd, "create_cli_context", lambda: object())
    monkeypatch.setattr(monitor_cmd, "JobsService", _FakeJobsService)
    monkeypatch.setattr(monitor_cmd, "WorkersService", _FakeWorkersService)
    monkeypatch.setattr(monitor_cmd.typer, "clear", lambda: None)
    monkeypatch.setattr(monitor_cmd.typer, "echo", lambda line: emitted.append(str(line)))

    def _raise_interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(monitor_cmd.time, "sleep", _raise_interrupt)

    monitor_cmd.monitor(interval_seconds=0.1)

    assert any(line == "[jobs]" for line in emitted)
    assert any(line == "[workers]" for line in emitted)
    assert any("job-one" in line for line in emitted)
    assert any("A100" in line for line in emitted)
