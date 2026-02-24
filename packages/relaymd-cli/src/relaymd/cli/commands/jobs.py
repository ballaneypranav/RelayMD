from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import typer
from relaymd.cli.config import load_settings
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Manage jobs.")
console = Console()


def _headers() -> dict[str, str]:
    return {"X-API-Token": load_settings().api_token}


def _orchestrator_base() -> str:
    return load_settings().orchestrator_url.rstrip("/")


def _status_style(status: str) -> str:
    styles = {
        "queued": "yellow",
        "assigned": "cyan",
        "running": "blue",
        "completed": "green",
        "failed": "red",
        "cancelled": "dim",
    }
    return styles.get(status, "white")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _age_label(timestamp: str | None) -> str:
    parsed = _parse_iso_datetime(timestamp)
    if parsed is None:
        return "-"
    seconds = int((datetime.now(UTC) - parsed).total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method,
            f"{_orchestrator_base()}{path}",
            headers=_headers(),
            **kwargs,
        )
        response.raise_for_status()
        return response


@app.command("list")
def list_jobs() -> None:
    try:
        jobs = _request("GET", "/jobs").json()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list jobs:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Jobs")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Assigned Worker")
    table.add_column("Last Checkpoint Age")

    for job in jobs:
        status = str(job.get("status", "unknown"))
        table.add_row(
            str(job.get("id", "-"))[:8],
            str(job.get("title", "-")),
            f"[{_status_style(status)}]{status}[/{_status_style(status)}]",
            str(job.get("assigned_worker_id") or "-")[:8],
            _age_label(job.get("last_checkpoint_at")),
        )

    console.print(table)


@app.command("status")
def job_status(job_id: str) -> None:
    try:
        job = _request("GET", f"/jobs/{job_id}").json()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to get job status:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    status = str(job.get("status", "unknown"))
    rows = [
        ("id", str(job.get("id", "-"))),
        ("title", str(job.get("title", "-"))),
        ("status", f"[{_status_style(status)}]{status}[/{_status_style(status)}]"),
        ("input_bundle_path", str(job.get("input_bundle_path", "-"))),
        ("latest_checkpoint_path", str(job.get("latest_checkpoint_path") or "-")),
        ("last_checkpoint_at", str(job.get("last_checkpoint_at") or "-")),
        ("assigned_worker_id", str(job.get("assigned_worker_id") or "-")),
        ("created_at", str(job.get("created_at") or "-")),
        ("updated_at", str(job.get("updated_at") or "-")),
    ]

    table = Table(title=f"Job {job_id}", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


@app.command("cancel")
def cancel_job(
    job_id: str,
    force: bool = typer.Option(False, "--force", help="Cancel running job."),
) -> None:
    try:
        path = f"/jobs/{job_id}"
        if force:
            path = f"{path}?force=true"
        _request("DELETE", path)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to cancel job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Cancelled job[/green] {job_id}")


@app.command("requeue")
def requeue_job(job_id: str) -> None:
    try:
        _request("POST", f"/jobs/{job_id}/requeue")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to requeue job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Requeued job[/green] {job_id}")
