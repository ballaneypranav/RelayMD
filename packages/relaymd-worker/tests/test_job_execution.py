from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from relaymd.worker.job_execution import JobExecution


def _cleanup_execution(execution: JobExecution) -> None:
    if execution.is_running():
        execution.kill()
        execution.wait(timeout_seconds=5)


def test_fatal_log_pattern_reports_supervision_failure(tmp_path: Path) -> None:
    execution = JobExecution(
        command=[sys.executable, "-c", "import time; time.sleep(60)"],
        workdir=tmp_path,
        checkpoint_glob_pattern="*.chk",
        checkpoint_b2_key="jobs/1/checkpoints/latest",
        fatal_log_path="payload.log",
        fatal_log_patterns=["Traceback"],
    )
    execution.start()
    try:
        (tmp_path / "payload.log").write_text("Traceback: child failed\n", encoding="utf-8")

        failure = execution.supervision_failure(now=1.0)

        assert failure is not None
        assert failure.reason == "fatal_log_match"
    finally:
        _cleanup_execution(execution)


def test_startup_progress_timeout_reports_supervision_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("relaymd.worker.job_execution.time.monotonic", lambda: 0.0)
    execution = JobExecution(
        command=[sys.executable, "-c", "import time; time.sleep(60)"],
        workdir=tmp_path,
        checkpoint_glob_pattern="*.chk",
        checkpoint_b2_key="jobs/1/checkpoints/latest",
        progress_glob_patterns=["progress"],
        startup_progress_timeout_seconds=10,
    )
    execution.start()
    try:
        failure = execution.supervision_failure(now=11.0)

        assert failure is not None
        assert failure.reason == "startup_progress_timeout"
    finally:
        _cleanup_execution(execution)


def test_progress_timeout_resets_when_matching_file_mtime_advances(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("relaymd.worker.job_execution.time.monotonic", lambda: 0.0)
    execution = JobExecution(
        command=[sys.executable, "-c", "import time; time.sleep(60)"],
        workdir=tmp_path,
        checkpoint_glob_pattern="*.chk",
        checkpoint_b2_key="jobs/1/checkpoints/latest",
        progress_glob_patterns=["progress"],
        progress_timeout_seconds=5,
    )
    execution.start()
    try:
        progress = tmp_path / "progress"
        progress.write_text("first\n", encoding="utf-8")
        os.utime(progress, (10.0, 10.0))
        assert execution.supervision_failure(now=2.0) is None

        progress.write_text("second\n", encoding="utf-8")
        os.utime(progress, (20.0, 20.0))
        assert execution.supervision_failure(now=6.0) is None
        assert execution.supervision_failure(now=10.0) is None

        failure = execution.supervision_failure(now=12.0)

        assert failure is not None
        assert failure.reason == "progress_timeout"
    finally:
        _cleanup_execution(execution)


def test_max_runtime_reports_supervision_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("relaymd.worker.job_execution.time.monotonic", lambda: 0.0)
    execution = JobExecution(
        command=[sys.executable, "-c", "import time; time.sleep(60)"],
        workdir=tmp_path,
        checkpoint_glob_pattern="*.chk",
        checkpoint_b2_key="jobs/1/checkpoints/latest",
        max_runtime_seconds=10,
    )
    execution.start()
    try:
        failure = execution.supervision_failure(now=10.0)

        assert failure is not None
        assert failure.reason == "max_runtime_exceeded"
    finally:
        _cleanup_execution(execution)


def test_request_terminate_reaches_child_process_group(tmp_path: Path) -> None:
    child_marker = tmp_path / "child-terminated"
    ready_marker = tmp_path / "child-ready"
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "\n".join(
            [
                "import pathlib",
                "import signal",
                "import time",
                f"marker = pathlib.Path({str(child_marker)!r})",
                f"ready = pathlib.Path({str(ready_marker)!r})",
                "def handle_term(signum, frame):",
                "    marker.write_text('terminated', encoding='utf-8')",
                "    raise SystemExit(0)",
                "signal.signal(signal.SIGTERM, handle_term)",
                "ready.write_text('ready', encoding='utf-8')",
                "while True:",
                "    time.sleep(0.1)",
            ]
        ),
        encoding="utf-8",
    )
    command = [
        "bash",
        "-c",
        f"{sys.executable} {child_script} & echo $! > child.pid; wait",
    ]
    execution = JobExecution(
        command=command,
        workdir=tmp_path,
        checkpoint_glob_pattern="*.chk",
        checkpoint_b2_key="jobs/1/checkpoints/latest",
    )
    execution.start()
    try:
        deadline = time.monotonic() + 5
        while not ready_marker.exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)

        execution.request_terminate()
        execution.wait(timeout_seconds=5)

        assert child_marker.read_text(encoding="utf-8") == "terminated"
    finally:
        _cleanup_execution(execution)
