from __future__ import annotations

import typer

from relaymd.cli.runtime_paths import resolve_paths

app = typer.Typer(help="Inspect RelayMD configuration paths.")


@app.command("show-paths")
def show_paths() -> None:
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

