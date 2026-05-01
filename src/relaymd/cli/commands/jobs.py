from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.jobs_service import JobsService

app = typer.Typer(help="Manage jobs.")
checkpoint_app = typer.Typer(help="Manage job checkpoints.")
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


@checkpoint_app.command("download")
def download_checkpoint(
    job_id: str,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Output file or directory path."),
    ] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = JobsService(create_cli_context()).download_latest_checkpoint(
            job_id=UUID(job_id),
            output=output,
        )
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            try:
                json.loads(str(exc))
                typer.echo(str(exc))
            except Exception:
                typer.echo(
                    json.dumps(
                        {
                            "error": {
                                "code": "checkpoint_download_failed",
                                "message": str(exc),
                            }
                        }
                    )
                )
        else:
            console.print(f"[red]Failed to download checkpoint:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(payload))
    else:
        console.print(f"[green]Downloaded checkpoint[/green] {payload['local_path']}")


app.add_typer(checkpoint_app, name="checkpoint")
