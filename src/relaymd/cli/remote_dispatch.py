from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from relaymd.cli.runtime_paths import RelaymdPaths, resolve_paths

REMOTE_DISPATCH_ENV = "RELAYMD_CLI_REMOTE_DISPATCH"

API_COMMANDS = {
    "submit",
    "jobs",
    "job",
    "workers",
    "worker",
    "monitor",
}


@dataclass(frozen=True)
class RemoteDispatchTarget:
    host: str
    command: list[str]
    remote_command: str


def current_host() -> str:
    return socket.gethostname().split(".", 1)[0]


def status_pairs(status_file: Path) -> dict[str, str]:
    if not status_file.is_file():
        return {}
    pairs: dict[str, str] = {}
    for line in status_file.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key] = value
    return pairs


def _parse_utc_timestamp(value: str) -> datetime | None:
    if not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_fresh(timestamp: str, *, stale_after_seconds: int, now: datetime | None = None) -> bool:
    parsed = _parse_utc_timestamp(timestamp)
    if parsed is None:
        return False
    reference = now or datetime.now(UTC)
    age_seconds = (reference - parsed).total_seconds()
    return 0 <= age_seconds <= stale_after_seconds


def _active_and_fresh(
    pairs: dict[str, str],
    *,
    service_prefix: str,
    stale_after_seconds: int,
) -> bool:
    return pairs.get(f"{service_prefix}_ACTIVE") == "1" and _is_fresh(
        pairs.get(f"{service_prefix}_HEARTBEAT_AT", ""),
        stale_after_seconds=stale_after_seconds,
    )


def _stale_after_seconds() -> int:
    raw = os.getenv("RELAYMD_HEARTBEAT_STALE_SECONDS", "120").strip()
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(value, 1)


def should_delegate_to_remote_host(
    *,
    args: list[str],
    paths: RelaymdPaths,
    current_host_name: str,
    env: dict[str, str] | None = None,
) -> str | None:
    active_env = env or os.environ
    if active_env.get(REMOTE_DISPATCH_ENV) == "1":
        return None
    if not args or args[0] not in API_COMMANDS or any(arg in {"-h", "--help"} for arg in args):
        return None

    pairs = status_pairs(paths.status_file)
    locked_host = (pairs.get("HOST") or "").strip()
    target_host = (paths.primary_host or locked_host).strip()
    if not target_host or target_host == current_host_name:
        return None

    if locked_host and locked_host != target_host:
        return None

    stale_after_seconds = _stale_after_seconds()
    if not _active_and_fresh(
        pairs,
        service_prefix="ORCHESTRATOR",
        stale_after_seconds=stale_after_seconds,
    ):
        return None
    if not _active_and_fresh(
        pairs,
        service_prefix="PROXY",
        stale_after_seconds=stale_after_seconds,
    ):
        return None

    return target_host


def _same_cli_executable(argv0: str) -> str:
    if not argv0:
        return "relaymd"
    candidate = Path(argv0).expanduser()
    if candidate.is_file():
        return str(candidate)
    resolved = shutil.which(argv0)
    return resolved or argv0


def build_remote_dispatch_target(
    *,
    argv: list[str],
    target_host: str,
    cwd: Path,
) -> RemoteDispatchTarget:
    executable = _same_cli_executable(argv[0] if argv else "relaymd")
    args = argv[1:] if argv else []
    remote_command = " ".join(
        [
            "cd",
            shlex.quote(str(cwd)),
            "&&",
            f"{REMOTE_DISPATCH_ENV}=1",
            shlex.quote(executable),
            *[shlex.quote(arg) for arg in args],
        ]
    )
    return RemoteDispatchTarget(
        host=target_host,
        command=["ssh", target_host, remote_command],
        remote_command=remote_command,
    )


def maybe_dispatch_from_argv(argv: list[str] | None = None) -> None:
    active_argv = list(sys.argv if argv is None else argv)
    paths = resolve_paths()
    target_host = should_delegate_to_remote_host(
        args=active_argv[1:],
        paths=paths,
        current_host_name=current_host(),
    )
    if target_host is None:
        return

    target = build_remote_dispatch_target(
        argv=active_argv,
        target_host=target_host,
        cwd=Path.cwd(),
    )
    try:
        result = subprocess.run(target.command, check=False)
    except FileNotFoundError as exc:
        raise SystemExit(127) from exc
    raise SystemExit(result.returncode)
