from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from relaymd.cli.commands.jobs_checkpoint import checkpoint_app
from relaymd.cli.commands.jobs_export import JOB_EXPORT_COLUMNS, job_to_export_row
from relaymd.cli.context import create_cli_context
from relaymd.cli.services.jobs_service import JobsService

app = typer.Typer(help="Manage jobs.")
console = Console()

JOB_LIST_COLUMNS: list[str] = [
    "id",
    "title",
    "status",
    "created_at",
    "assigned_worker_id",
]



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


def _render_jobs_plain_lines(jobs: list[dict[str, Any]]) -> list[str]:
    lines = ["\t".join(JOB_LIST_COLUMNS)]
    for job in jobs:
        lines.append("\t".join(str(job.get(column) or "-") for column in JOB_LIST_COLUMNS))
    return lines


def _csv_stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True)




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
        help="Format output as a rich table instead of parsed text.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    try:
        jobs = JobsService(create_cli_context()).list_jobs()
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "list_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to list jobs:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    jobs_payload = [job.to_dict() for job in jobs]
    if json_mode:
        typer.echo(json.dumps({"jobs": jobs_payload}))
        return
    if pretty:
        table = Table(title="Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Created At")
        table.add_column("Worker ID")
        for job in jobs_payload:
            status = str(job.get("status", "-"))
            status_formatted = f"[{_status_style(status)}]{status}[/{_status_style(status)}]"
            table.add_row(
                str(job.get("id") or "-"),
                str(job.get("title") or "-"),
                status_formatted,
                str(job.get("created_at") or "-"),
                str(job.get("assigned_worker_id") or "-"),
            )
        console.print(table)
    else:
        for line in _render_jobs_plain_lines(jobs_payload):
            typer.echo(line)


@app.command("show")
def job_status(job_id: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    try:
        job = JobsService(create_cli_context()).get_job(job_id=UUID(job_id))
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "get_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to get job status:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(job.to_dict()))
        return
    console.print(_render_job_status_panel(job_id, job.to_dict()))


app.command("status", hidden=True)(job_status)


@app.command("cancel")
def cancel_job(
    job_id: str,
    force: bool = typer.Option(False, "--force", help="Cancel running job."),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        job = JobsService(create_cli_context()).cancel_job(job_id=UUID(job_id), force=force)
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "cancel_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to cancel job:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(job.to_dict()))
        return
    console.print(f"[green]Cancelled job[/green] {job_id}")


@app.command("requeue")
def requeue_job(job_id: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    try:
        response = JobsService(create_cli_context()).requeue_job(job_id=UUID(job_id))
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "requeue_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to requeue job:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(response.to_dict()))
        return
    console.print(f"[green]Requeued job[/green] {response.id}")


_PRUNE_STATUSES = ["completed", "failed", "cancelled"]


@app.command("prune")
def prune_jobs(
    statuses: Annotated[
        list[str],
        typer.Option("--status", help="Terminal statuses to prune: completed, failed, cancelled."),
    ] = _PRUNE_STATUSES,
    older_than: Annotated[
        int,
        typer.Option("--older-than", min=1, help="Minimum age in days (based on last update)."),
    ] = 30,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Report how many jobs would be deleted without deleting."),
    ] = False,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Hard-delete completed, failed, or cancelled jobs older than N days."""
    invalid = [s for s in statuses if s not in _PRUNE_STATUSES]
    if invalid:
        msg = f"Invalid status values: {invalid}. Must be one of: {_PRUNE_STATUSES}"
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "invalid_status", "message": msg}}))
        else:
            console.print(f"[red]{escape(msg)}[/red]")
        raise typer.Exit(code=1)

    service = JobsService(create_cli_context())

    if dry_run:
        try:
            all_jobs = service.list_jobs()
        except Exception as exc:  # noqa: BLE001
            if json_mode:
                typer.echo(json.dumps({"error": {"code": "list_failed", "message": str(exc)}}))
            else:
                console.print(f"[red]Failed to list jobs:[/red] {escape(str(exc))}")
            raise typer.Exit(code=1) from exc
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=older_than)
        count = sum(
            1
            for job in all_jobs
            if str(job.status) in statuses
            and job.updated_at is not None
            and job.updated_at < cutoff
        )
        if json_mode:
            typer.echo(json.dumps({"dry_run": True, "would_delete": count}))
        else:
            typer.echo(f"Would delete {count} job(s) older than {older_than} day(s).")
        return

    try:
        deleted = service.prune_jobs(statuses=statuses, older_than_days=older_than)
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "prune_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to prune jobs:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps({"deleted": deleted}))
    else:
        typer.echo(f"Deleted {deleted} job(s) older than {older_than} day(s).")


@app.command("export-csv")
def export_jobs_csv(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Output CSV path. Defaults to relaymd-jobs.csv in the current directory.",
        ),
    ] = Path("relaymd-jobs.csv"),
) -> None:
    try:
        jobs = JobsService(create_cli_context()).list_jobs()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list jobs:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    jobs_payload = [job.to_dict() for job in jobs]
    now = datetime.now(UTC)
    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=JOB_EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for job in jobs_payload:
            row = job_to_export_row(job, now)
            writer.writerow(
                {column: _csv_stringify(row.get(column)) for column in JOB_EXPORT_COLUMNS}
            )

    typer.echo(f"Wrote {len(jobs_payload)} job(s) to {output.resolve()}")

app.add_typer(checkpoint_app, name="checkpoint")
