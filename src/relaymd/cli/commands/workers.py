from __future__ import annotations

from datetime import UTC, datetime

import httpx
import typer
from relaymd.cli.config import load_settings
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="List workers.")
console = Console()


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


@app.command("list")
def list_workers() -> None:
    settings = load_settings()
    headers = {"X-API-Token": settings.api_token}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{settings.orchestrator_url.rstrip('/')}/workers",
                headers=headers,
            )
            response.raise_for_status()
            workers = response.json()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list workers:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Workers")
    table.add_column("ID")
    table.add_column("Platform")
    table.add_column("GPU Model")
    table.add_column("GPU Count")
    table.add_column("VRAM (GB)")
    table.add_column("Last Heartbeat")
    table.add_column("Status")

    now = datetime.now(UTC)
    for worker in workers:
        last_heartbeat_raw = str(worker.get("last_heartbeat", ""))
        last_heartbeat = _parse_iso_datetime(last_heartbeat_raw)
        age_seconds = (now - last_heartbeat).total_seconds()
        status = "stale" if age_seconds > 120 else "healthy"
        status_color = "red" if status == "stale" else "green"

        table.add_row(
            str(worker.get("id", "-"))[:8],
            str(worker.get("platform", "-")),
            str(worker.get("gpu_model", "-")),
            str(worker.get("gpu_count", "-")),
            str(worker.get("vram_gb", "-")),
            last_heartbeat_raw,
            f"[{status_color}]{status}[/{status_color}]",
        )

    console.print(table)
