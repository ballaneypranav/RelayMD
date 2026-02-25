from __future__ import annotations

import httpx
import typer
from relaymd_api_client.api.default import list_workers_workers_get
from relaymd_api_client.client import Client as RelaymdApiClient
from relaymd_api_client.models.worker_read import WorkerRead
from rich.console import Console
from rich.table import Table

from relaymd.cli.config import load_settings

app = typer.Typer(help="List workers.")
console = Console()


def _api_client() -> RelaymdApiClient:
    settings = load_settings()
    return RelaymdApiClient(
        base_url=settings.orchestrator_url.rstrip("/"),
        timeout=httpx.Timeout(30.0),
        raise_on_unexpected_status=True,
    )


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
    settings = load_settings()

    try:
        with _api_client() as client:
            workers = list_workers_workers_get.sync(
                client=client,
                x_api_token=settings.api_token,
            )
        if workers is None or not isinstance(workers, list):
            raise RuntimeError("Failed to parse list workers response")
        if workers and not isinstance(workers[0], WorkerRead):
            raise RuntimeError("Unexpected response model for list workers")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list workers:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(_render_workers_table([worker.to_dict() for worker in workers]))
