from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass
class JobExecutionResult:
    status: Literal["completed", "failed", "cancelled"]
    latest_checkpoint_b2_key: str | None


class JobExecution:
    def __init__(
        self,
        *,
        command: list[str],
        workdir: Path,
        checkpoint_glob_pattern: str,
        checkpoint_b2_key: str,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._checkpoint_glob_pattern = checkpoint_glob_pattern
        self._checkpoint_b2_key = checkpoint_b2_key
        self._process: subprocess.Popen[Any] | None = None
        self._last_seen_checkpoint_mtime: float | None = None
        self._terminate_requested = False

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("execution already started")
        self._process = subprocess.Popen(  # noqa: S603
            self._command,
            cwd=self._workdir,
        )

    def is_running(self) -> bool:
        process = self._require_process()
        return process.poll() is None

    def poll_exit_code(self) -> int | None:
        return self._require_process().poll()

    def iter_new_checkpoints(self) -> Iterator[Path]:
        latest = self._find_latest_checkpoint()
        if latest is None:
            return

        latest_mtime = latest.stat().st_mtime
        if (
            self._last_seen_checkpoint_mtime is not None
            and latest_mtime <= self._last_seen_checkpoint_mtime
        ):
            return

        self._last_seen_checkpoint_mtime = latest_mtime
        yield latest

    def request_terminate(self) -> None:
        process = self._require_process()
        self._terminate_requested = True
        process.terminate()

    def wait(self, timeout_seconds: float) -> int | None:
        process = self._require_process()
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return None

    def result(self) -> JobExecutionResult:
        exit_code = self.poll_exit_code()
        if exit_code is None:
            raise RuntimeError("Execution result requested before process exit")

        status: Literal["completed", "failed", "cancelled"]
        if self._terminate_requested:
            status = "cancelled"
        elif exit_code == 0:
            status = "completed"
        else:
            status = "failed"

        latest_checkpoint = self._find_latest_checkpoint()
        return JobExecutionResult(
            status=status,
            latest_checkpoint_b2_key=self._checkpoint_b2_key if latest_checkpoint else None,
        )

    def latest_checkpoint(self) -> Path | None:
        return self._find_latest_checkpoint()

    def _find_latest_checkpoint(self) -> Path | None:
        candidates = [
            path for path in self._workdir.glob(self._checkpoint_glob_pattern) if path.is_file()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _require_process(self) -> subprocess.Popen[Any]:
        if self._process is None:
            raise RuntimeError("execution is not started")
        return self._process
