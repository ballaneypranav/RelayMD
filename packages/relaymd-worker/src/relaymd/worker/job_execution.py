from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from stat import S_ISREG
from typing import Any, Literal


@dataclass
class JobExecutionResult:
    status: Literal["completed", "failed", "cancelled"]
    latest_checkpoint_b2_key: str | None


@dataclass(frozen=True)
class JobSupervisionFailure:
    reason: Literal[
        "max_runtime_exceeded",
        "startup_progress_timeout",
        "progress_timeout",
        "fatal_log_match",
    ]
    detail: str


class JobExecution:
    def __init__(
        self,
        *,
        command: list[str],
        workdir: Path,
        checkpoint_glob_pattern: str,
        checkpoint_b2_key: str,
        progress_glob_patterns: list[str] | None = None,
        startup_progress_timeout_seconds: int | None = None,
        progress_timeout_seconds: int | None = None,
        max_runtime_seconds: int | None = None,
        fatal_log_path: str | None = None,
        fatal_log_patterns: list[str] | None = None,
    ) -> None:
        self._command = command
        self._workdir = workdir
        self._checkpoint_glob_pattern = checkpoint_glob_pattern
        self._checkpoint_b2_key = checkpoint_b2_key
        self._progress_glob_patterns = progress_glob_patterns or []
        self._startup_progress_timeout_seconds = startup_progress_timeout_seconds
        self._progress_timeout_seconds = progress_timeout_seconds
        self._max_runtime_seconds = max_runtime_seconds
        self._fatal_log_path = fatal_log_path
        self._fatal_log_patterns = fatal_log_patterns or []
        self._process: subprocess.Popen[Any] | None = None
        self._started_at: float | None = None
        self._last_seen_checkpoint_mtime: float | None = None
        self._last_seen_progress_mtime: float | None = None
        self._last_progress_at: float | None = None
        self._terminate_requested = False
        self._supervision_failure: JobSupervisionFailure | None = None

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("execution already started")
        self._started_at = time.monotonic()
        progress = self._find_latest_progress_with_mtime()
        if progress is not None:
            self._last_seen_progress_mtime = progress[1]
            self._last_progress_at = self._started_at
        self._process = subprocess.Popen(  # noqa: S603
            self._command,
            cwd=self._workdir,
            start_new_session=True,
        )

    def is_running(self) -> bool:
        process = self._require_process()
        return process.poll() is None

    def poll_exit_code(self) -> int | None:
        return self._require_process().poll()

    def supervision_failure(self, *, now: float | None = None) -> JobSupervisionFailure | None:
        if self._supervision_failure is not None:
            return self._supervision_failure
        if self.poll_exit_code() is not None:
            return None

        started_at = self._require_started_at()
        now = time.monotonic() if now is None else now

        fatal_log_failure = self._fatal_log_failure()
        if fatal_log_failure is not None:
            self._supervision_failure = fatal_log_failure
            return fatal_log_failure

        if self._max_runtime_seconds is not None and now - started_at >= self._max_runtime_seconds:
            self._supervision_failure = JobSupervisionFailure(
                reason="max_runtime_exceeded",
                detail=f"runtime exceeded {self._max_runtime_seconds} seconds",
            )
            return self._supervision_failure

        progress = self._find_latest_progress_with_mtime()
        if progress is not None:
            _, progress_mtime = progress
            if (
                self._last_seen_progress_mtime is None
                or progress_mtime > self._last_seen_progress_mtime
            ):
                self._last_seen_progress_mtime = progress_mtime
                self._last_progress_at = now

        if self._last_progress_at is None:
            if (
                self._startup_progress_timeout_seconds is not None
                and now - started_at >= self._startup_progress_timeout_seconds
            ):
                self._supervision_failure = JobSupervisionFailure(
                    reason="startup_progress_timeout",
                    detail=(
                        "no progress files matched within "
                        f"{self._startup_progress_timeout_seconds} seconds"
                    ),
                )
                return self._supervision_failure
            return None

        if (
            self._progress_timeout_seconds is not None
            and now - self._last_progress_at >= self._progress_timeout_seconds
        ):
            self._supervision_failure = JobSupervisionFailure(
                reason="progress_timeout",
                detail=f"no progress update within {self._progress_timeout_seconds} seconds",
            )
            return self._supervision_failure

        return None

    def iter_new_checkpoints(self) -> Iterator[Path]:
        latest = self._find_latest_checkpoint_with_mtime()
        if latest is None:
            return

        latest_path, latest_mtime = latest
        if (
            self._last_seen_checkpoint_mtime is not None
            and latest_mtime <= self._last_seen_checkpoint_mtime
        ):
            return

        self._last_seen_checkpoint_mtime = latest_mtime
        yield latest_path

    def request_terminate(self) -> None:
        process = self._require_process()
        self._terminate_requested = True
        self._signal_process_group(signal.SIGTERM, fallback=process.terminate)

    def wait(self, timeout_seconds: float) -> int | None:
        process = self._require_process()
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return None

    def kill(self) -> None:
        process = self._require_process()
        self._signal_process_group(signal.SIGKILL, fallback=process.kill)

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
        latest = self._find_latest_checkpoint_with_mtime()
        if latest is None:
            return None
        return latest[0]

    def _find_latest_checkpoint_with_mtime(self) -> tuple[Path, float] | None:
        return self._find_latest_file_with_mtime([self._checkpoint_glob_pattern])

    def _find_latest_progress_with_mtime(self) -> tuple[Path, float] | None:
        return self._find_latest_file_with_mtime(self._progress_glob_patterns)

    def _find_latest_file_with_mtime(self, patterns: list[str]) -> tuple[Path, float] | None:
        latest: tuple[Path, float] | None = None
        for pattern in patterns:
            for path in self._workdir.glob(pattern):
                try:
                    stat_result = path.stat()
                except OSError:
                    continue
                if not S_ISREG(stat_result.st_mode):
                    continue

                path_mtime = stat_result.st_mtime
                if latest is None or path_mtime > latest[1]:
                    latest = (path, path_mtime)
        return latest

    def _fatal_log_failure(self) -> JobSupervisionFailure | None:
        if self._fatal_log_path is None or not self._fatal_log_patterns:
            return None

        log_path = self._workdir / self._fatal_log_path
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        for pattern in self._fatal_log_patterns:
            if pattern in log_text:
                return JobSupervisionFailure(
                    reason="fatal_log_match",
                    detail=f"fatal log pattern matched: {pattern}",
                )
        return None

    def _signal_process_group(self, signum: int, *, fallback) -> None:
        process = self._require_process()
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        except OSError:
            fallback()
            return

        try:
            os.killpg(pgid, signum)
        except ProcessLookupError:
            return
        except OSError:
            fallback()

    def _require_started_at(self) -> float:
        if self._started_at is None:
            raise RuntimeError("execution is not started")
        return self._started_at

    def _require_process(self) -> subprocess.Popen[Any]:
        if self._process is None:
            raise RuntimeError("execution is not started")
        return self._process
