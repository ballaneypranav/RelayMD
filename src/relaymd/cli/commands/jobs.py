from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from relaymd_api_client.api.default import (
    cancel_job_jobs_job_id_delete,
    get_job_jobs_job_id_get,
    list_jobs_jobs_get,
    requeue_job_jobs_job_id_requeue_post,
)
from relaymd_api_client.client import Client as RelaymdApiClient
from relaymd_api_client.models.http_validation_error import HTTPValidationError
from relaymd_api_client.models.job_read import JobRead

from relaymd.cli.config import load_settings

app = typer.Typer(help="Manage jobs.")
console = Console()


def _headers() -> dict[str, str]:
    return {"X-API-Token": load_settings().api_token}


def _orchestrator_base() -> str:
    return load_settings().orchestrator_url.rstrip("/")


def _token() -> str:
    return load_settings().api_token


def _api_client() -> RelaymdApiClient:
    return RelaymdApiClient(
        base_url=_orchestrator_base(),
        timeout=httpx.Timeout(30.0),
        raise_on_unexpected_status=True,
    )


def _status_style(status: str) -> str:
    styles = {
        "queued": "blue",
        "assigned": "cyan",
        "running": "yellow",
        "completed": "green",
        "failed": "red",
        "cancelled": "red",
    }
    return styles.get(status, "white")


def _short_id(value: str | None) -> str:
    if not value:
        return "—"
    return str(value)[:8]


def _render_jobs_table(jobs: list[dict[str, Any]]) -> Table:
    table = Table(title="Jobs")
    table.add_column("ID", justify="right")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Assigned Worker")

    for job in jobs:
        status = str(job.get("status", "unknown"))
        style = _status_style(status)
        table.add_row(
            _short_id(job.get("id")),
            str(job.get("title", "-")),
            f"[{style}]{status}[/{style}]",
            str(job.get("created_at") or "-"),
            _short_id(job.get("assigned_worker_id")),
        )

    return table


def _render_job_status_panel(job_id: str, job: dict[str, Any]) -> Panel:
    status = str(job.get("status", "unknown"))
    rows = [
        ("ID", str(job.get("id", "-"))),
        ("Title", str(job.get("title", "-"))),
        ("Status", f"[{_status_style(status)}]{status}[/{_status_style(status)}]"),
        ("Input Bundle", str(job.get("input_bundle_path", "-"))),
        ("Latest Checkpoint", str(job.get("latest_checkpoint_path") or "-")),
        ("Last Checkpoint", str(job.get("last_checkpoint_at") or "-")),
        ("Assigned Worker", str(job.get("assigned_worker_id") or "-")),
        ("Created", str(job.get("created_at") or "-")),
        ("Updated", str(job.get("updated_at") or "-")),
    ]

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for key, value in rows:
        table.add_row(key, value)

    return Panel(table, title=f"Job {job_id}")


@app.command("list")
def list_jobs() -> None:
    try:
        with _api_client() as client:
            jobs = list_jobs_jobs_get.sync(client=client, x_api_token=_token())
        if jobs is None or not isinstance(jobs, list):
            raise RuntimeError("Failed to parse list jobs response")
        if jobs and not isinstance(jobs[0], JobRead):
            raise RuntimeError("Unexpected response model for list jobs")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list jobs:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(_render_jobs_table([job.to_dict() for job in jobs]))


@app.command("status")
def job_status(job_id: str) -> None:
    try:
        with _api_client() as client:
            job = get_job_jobs_job_id_get.sync(
                job_id=UUID(job_id),
                client=client,
                x_api_token=_token(),
            )
        if job is None or not isinstance(job, JobRead):
            raise RuntimeError("Failed to parse get job response")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to get job status:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(_render_job_status_panel(job_id, job.to_dict()))


@app.command("cancel")
def cancel_job(
    job_id: str,
    force: bool = typer.Option(False, "--force", help="Cancel running job."),
) -> None:
    try:
        with _api_client() as client:
            response = cancel_job_jobs_job_id_delete.sync(
                job_id=UUID(job_id),
                client=client,
                force=force,
                x_api_token=_token(),
            )
        if isinstance(response, HTTPValidationError):
            raise RuntimeError(response.to_dict())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to cancel job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Cancelled job[/green] {job_id}")


@app.command("requeue")
def requeue_job(job_id: str) -> None:
    try:
        with _api_client() as client:
            response = requeue_job_jobs_job_id_requeue_post.sync(
                job_id=UUID(job_id),
                client=client,
                x_api_token=_token(),
            )
        if response is None or not isinstance(response, JobRead):
            raise RuntimeError("Failed to parse requeue response")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to requeue job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Requeued job[/green] {response.id}")
