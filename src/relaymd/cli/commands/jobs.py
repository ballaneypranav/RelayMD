from __future__ import annotations

from typing import Any
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.jobs_service import JobsService

app = typer.Typer(help="Manage jobs.")
console = Console()


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
        return "-"
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


def _render_jobs_plain_lines(jobs: list[dict[str, Any]]) -> list[str]:
    lines = ["id\ttitle\tstatus\tcreated_at\tassigned_worker_id"]
    for job in jobs:
        lines.append(
            "\t".join(
                [
                    str(job.get("id") or "-"),
                    str(job.get("title") or "-"),
                    str(job.get("status") or "-"),
                    str(job.get("created_at") or "-"),
                    str(job.get("assigned_worker_id") or "-"),
                ]
            )
        )
    return lines


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
def list_jobs(
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Print a rich table instead of default tab-separated text.",
    ),
) -> None:
    try:
        jobs = JobsService(create_cli_context()).list_jobs()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list jobs:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    jobs_payload = [job.to_dict() for job in jobs]
    if pretty:
        console.print(_render_jobs_table(jobs_payload))
        return

    for line in _render_jobs_plain_lines(jobs_payload):
        typer.echo(line)


@app.command("status")
def job_status(job_id: str) -> None:
    try:
        job = JobsService(create_cli_context()).get_job(job_id=UUID(job_id))
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
        JobsService(create_cli_context()).cancel_job(job_id=UUID(job_id), force=force)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to cancel job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Cancelled job[/green] {job_id}")


@app.command("requeue")
def requeue_job(job_id: str) -> None:
    try:
        response = JobsService(create_cli_context()).requeue_job(job_id=UUID(job_id))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to requeue job:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Requeued job[/green] {response.id}")
