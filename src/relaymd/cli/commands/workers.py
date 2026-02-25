from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.workers_service import WorkersService

app = typer.Typer(help="List workers.")
console = Console()


def _short_id(value: str | None) -> str:
    if not value:
        return "—"
    return str(value)[:8]


def _status_style(status: str) -> str:
    styles = {
        "idle": "green",
        "busy": "yellow",
    }
    return styles.get(status, "white")


def _render_workers_table(workers: list[dict[str, object]]) -> Table:
    table = Table(title="Workers")
    table.add_column("ID", justify="right")
    table.add_column("Platform")
    table.add_column("GPU")
    table.add_column("VRAM")
    table.add_column("Last Heartbeat")
    table.add_column("Jobs Completed")
    table.add_column("Status")

    for worker in workers:
        status = str(worker.get("status") or "unknown")
        style = _status_style(status)
        worker_id = worker.get("id")
        worker_id_str = worker_id if isinstance(worker_id, str) else None
        table.add_row(
            _short_id(worker_id_str),
            str(worker.get("platform") or "-"),
            str(worker.get("gpu_model") or "-"),
            str(worker.get("vram_gb") or "-"),
            str(worker.get("last_heartbeat") or "-"),
            str(worker.get("jobs_completed") or "0"),
            f"[{style}]{status}[/{style}]",
        )

    return table


@app.command("list")
def list_workers() -> None:
    try:
        workers = WorkersService(create_cli_context()).list_workers()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list workers:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(_render_workers_table([worker.to_dict() for worker in workers]))
