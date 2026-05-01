from __future__ import annotations

import json

import typer

from relaymd.cli.diagnostics import collect_readiness
from relaymd.cli.runtime_paths import resolve_paths

app = typer.Typer(help="Inspect RelayMD configuration paths.")


@app.command("show-paths")
def show_paths(
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Print the resolved install, config, state, and log paths."""
    paths = resolve_paths()
    rows = [
        ("service_root", paths.service_root),
        ("data_root", paths.data_root),
        ("current", paths.current_link),
        ("yaml", paths.yaml_config),
        ("env", paths.env_file),
        ("status", paths.status_file),
        ("logs", paths.data_root / "logs"),
        ("service_logs", paths.service_log_dir),
        ("orchestrator_log", paths.orchestrator_wrapper_log),
        ("proxy_log", paths.proxy_wrapper_log),
    ]
    if json_mode:
        payload = {
            "service_root": str(paths.service_root),
            "data_root": str(paths.data_root),
            "config_path": str(paths.yaml_config),
            "env_path": str(paths.env_file),
            "status_path": str(paths.status_file),
            "logs_dir": str(paths.service_log_dir),
            "current_release": str(paths.current_release),
        }
        typer.echo(json.dumps(payload))
        return

    for key, value in rows:
        typer.echo(f"{key}\t{value}")


@app.command("shell-init")
def shell_init() -> None:
    """Print shell helpers for interactive directory changes."""
    typer.echo(
        """
relaymd_cd() {
  if [ "$#" -ne 1 ]; then
    printf 'usage: relaymd_cd data|config|logs\\n' >&2
    return 2
  fi
  case "$1" in
    data|config|logs) cd "$(relaymd path "$1")" ;;
    *) printf 'usage: relaymd_cd data|config|logs\\n' >&2; return 2 ;;
  esac
}
""".strip()
    )


@app.command("diagnose", hidden=True)
def diagnose(
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Emit internal readiness diagnostics for service wrappers."""
    readiness = collect_readiness()
    if json_mode:
        typer.echo(json.dumps(readiness, sort_keys=True))
        return

    for name, status in readiness.items():
        if name == "_ok" or not isinstance(status, dict):
            continue
        state = "ok" if status.get("ok") else "fail"
        typer.echo(f"{name}\t{state}")
