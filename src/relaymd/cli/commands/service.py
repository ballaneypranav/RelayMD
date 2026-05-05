from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Annotated

import typer

from relaymd.cli.runtime_paths import RelaymdPaths, resolve_paths

ServiceName = str


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise typer.Exit(code=127) from exc
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc


def _service_script(name: str, paths: RelaymdPaths) -> str:
    candidate = paths.service_root / "bin" / name
    if candidate.exists():
        return str(candidate)
    return name


def _status_pairs(status_file: Path) -> dict[str, str]:
    if not status_file.is_file():
        return {}
    pairs: dict[str, str] = {}
    for line in status_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            pairs[key] = value
    return pairs


def _write_status_pairs(status_file: Path, updates: dict[str, str]) -> None:
    pairs = _status_pairs(status_file)
    pairs.update(updates)
    pairs["UPDATED_BY"] = os.getenv("USER", "unknown")
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        "".join(f"{key}={value}\n" for key, value in pairs.items()),
        encoding="utf-8",
    )


def _current_host() -> str:
    return socket.gethostname().split(".", 1)[0]


def _ensure_down_allowed(paths: RelaymdPaths, *, force: bool) -> None:
    pairs = _status_pairs(paths.status_file)
    locked_host = pairs.get("HOST", "")
    active = pairs.get("ORCHESTRATOR_ACTIVE") == "1" or pairs.get("PROXY_ACTIVE") == "1"
    current_host = _current_host()
    expected_host = paths.primary_host or locked_host
    if expected_host and expected_host != current_host and active and not force:
        typer.echo(
            f"Refusing to stop on {current_host}: status indicates active RelayMD service on "
            f"{expected_host}. Use --force only after confirming it is inactive.",
            err=True,
        )
        raise typer.Exit(code=1)


def _tmux_kill(session_name: str) -> None:
    try:
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=False)
    except FileNotFoundError as exc:
        typer.echo("tmux is required to stop RelayMD service sessions.", err=True)
        raise typer.Exit(code=127) from exc


ForceOption = Annotated[
    bool,
    typer.Option("--force", "-f", help="Override host pin/lock checks."),
]
ServiceOption = Annotated[
    ServiceName,
    typer.Option("--service", help="Service name."),
]


def up(force: ForceOption = False) -> None:
    """Start the installed RelayMD orchestrator and dashboard proxy services."""
    paths = resolve_paths()
    force_arg = ["--force"] if force else []
    _run([_service_script("relaymd-service-up", paths), *force_arg])
    _run([_service_script("relaymd-service-proxy", paths), *force_arg])


def down(
    force: ForceOption = False,
) -> None:
    """Stop the installed RelayMD orchestrator and dashboard proxy services."""
    paths = resolve_paths()
    _ensure_down_allowed(paths, force=force)
    _tmux_kill(paths.proxy_session)
    _tmux_kill(paths.orchestrator_session)
    _write_status_pairs(
        paths.status_file,
        {
            "HOST": _current_host(),
            "ORCHESTRATOR_ACTIVE": "0",
            "PROXY_ACTIVE": "0",
        },
    )
    typer.echo(
        f"stopped RelayMD service sessions: {paths.orchestrator_session}, {paths.proxy_session}"
    )


def restart(
    force: ForceOption = False,
) -> None:
    """Restart the installed RelayMD orchestrator and dashboard proxy services."""
    down(force=force)
    up(force=force)


def status(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed status fields."),
    ] = False,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable ANSI color output."),
    ] = False,
) -> None:
    """Show installed RelayMD service health."""
    paths = resolve_paths()
    command = [_service_script("relaymd-service-status", paths)]
    if verbose:
        command.append("--verbose")
    if json_mode:
        command.append("--json")
    if no_color:
        command.append("--no-color")
    _run(command)


def _log_paths(paths: RelaymdPaths, service: ServiceName) -> list[Path]:
    if service == "orchestrator":
        return [paths.orchestrator_wrapper_log]
    if service == "proxy":
        return [paths.proxy_wrapper_log]
    return [paths.orchestrator_wrapper_log, paths.proxy_wrapper_log]


def logs(
    service: ServiceOption = "all",
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Follow log output."),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("-n", min=0, help="Number of trailing lines to print."),
    ] = 80,
) -> None:
    """Show RelayMD service wrapper logs."""
    if service not in {"orchestrator", "proxy", "all"}:
        raise typer.BadParameter("service must be one of: orchestrator, proxy, all")
    paths = resolve_paths()
    log_paths = _log_paths(paths, service)
    if follow:
        _run(["tail", "-n", str(lines), "-f", *[str(path) for path in log_paths]])
        return

    for index, log_path in enumerate(log_paths):
        if len(log_paths) > 1:
            if index:
                typer.echo("")
            typer.echo(f"==> {log_path} <==")
        if not log_path.is_file():
            typer.echo(f"missing log file: {log_path}", err=True)
            continue
        tail = deque(
            log_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            maxlen=lines,
        )
        for line in tail:
            typer.echo(line)


def attach(
    service: ServiceOption = "orchestrator",
) -> None:
    """Attach to a RelayMD service tmux session."""
    if service not in {"orchestrator", "proxy"}:
        raise typer.BadParameter("service must be one of: orchestrator, proxy")
    paths = resolve_paths()
    session_name = paths.proxy_session if service == "proxy" else paths.orchestrator_session
    _run(["tmux", "attach", "-t", session_name])


def clean_scripts(
    older_than: Annotated[
        int,
        typer.Option("--older-than", min=1, help="Delete scripts older than this many days."),
    ] = 30,
    log_dir: Annotated[
        str | None,
        typer.Option("--log-dir", help="Override RELAYMD_LOG_DIRECTORY for script location."),
    ] = None,
) -> None:
    """Delete sbatch submission scripts older than N days from the orchestrator log directory."""
    resolved = log_dir or os.environ.get("RELAYMD_LOG_DIRECTORY")
    if not resolved:
        typer.echo(
            "error: RELAYMD_LOG_DIRECTORY is not set and --log-dir was not provided.", err=True
        )
        raise typer.Exit(code=1)
    scripts_dir = Path(resolved) / "slurm"
    if not scripts_dir.is_dir():
        typer.echo(f"No scripts directory found at {scripts_dir}")
        return
    cutoff = time.time() - older_than * 86400
    deleted = 0
    for script in scripts_dir.glob("*.sbatch"):
        if script.stat().st_mtime < cutoff:
            script.unlink()
            deleted += 1
    if deleted:
        typer.echo(f"Deleted {deleted} sbatch script(s) from {scripts_dir}")
    else:
        typer.echo(f"No scripts older than {older_than} day(s) in {scripts_dir}")


def clean_logs(
    service: ServiceOption = "all",
) -> None:
    """Truncate RelayMD service wrapper log files."""
    if service not in {"orchestrator", "proxy", "all"}:
        raise typer.BadParameter("service must be one of: orchestrator, proxy, all")
    paths = resolve_paths()
    for log_path in _log_paths(paths, service):
        if not log_path.is_file():
            typer.echo(f"skipped (missing): {log_path}")
            continue
        log_path.open("w").close()
        typer.echo(f"Truncated: {log_path}")


def prune_releases(
    keep: Annotated[
        int,
        typer.Option("--keep", min=1, help="Number of most-recent releases to keep."),
    ] = 3,
) -> None:
    """Remove old release directories, keeping the N most recent."""
    paths = resolve_paths()
    releases_dir = paths.releases_dir
    if not releases_dir.is_dir():
        typer.echo(f"No releases directory found at {releases_dir}")
        return
    try:
        current_target = paths.current_link.resolve()
    except Exception:  # noqa: BLE001
        current_target = None

    candidates = sorted(
        (d for d in releases_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    # Keep the N most recent by mtime, and always protect the current symlink target.
    to_keep = set(candidates[:keep])
    if current_target:
        for candidate in candidates:
            if candidate.resolve() == current_target:
                to_keep.add(candidate)
                break

    deleted = 0
    for candidate in candidates:
        if candidate not in to_keep:
            shutil.rmtree(candidate)
            typer.echo(f"Removed: {candidate}")
            deleted += 1
    if deleted:
        typer.echo(f"Removed {deleted} old release(s).")
    else:
        typer.echo("No releases to remove.")


def upgrade(
    release: Annotated[
        str,
        typer.Argument(help="Release version/tag to pull and activate."),
    ] = "latest",
    orchestrator_image: Annotated[
        str | None,
        typer.Option("--orchestrator-image", help="Explicit orchestrator image URI."),
    ] = None,
    worker_image: Annotated[
        str | None,
        typer.Option("--worker-image", help="Explicit worker image URI."),
    ] = None,
    cli_uri: Annotated[
        str | None,
        typer.Option("--cli-uri", help="Explicit RelayMD CLI binary URI/path."),
    ] = None,
) -> None:
    """Pull and activate a RelayMD release."""
    paths = resolve_paths()
    command = [_service_script("relaymd-service-pull", paths), release]
    if orchestrator_image or worker_image:
        if not orchestrator_image or not worker_image:
            raise typer.BadParameter(
                "--orchestrator-image and --worker-image must be used together"
            )
        command.extend([orchestrator_image, worker_image])
    env = os.environ.copy()
    if cli_uri:
        env["RELAYMD_CLI_URI"] = cli_uri
    try:
        subprocess.run(command, check=True, env=env)
    except FileNotFoundError as exc:
        raise typer.Exit(code=127) from exc
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(code=exc.returncode) from exc
