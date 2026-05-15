from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.markup import escape

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.jobs_service import JobsService

checkpoint_app = typer.Typer(help="Manage job checkpoints.")
console = Console()


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


@checkpoint_app.command("download-file")
def download_checkpoint_file(
    job_id: str,
    relative_path: str,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Output file or directory path."),
    ] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = JobsService(create_cli_context()).download_checkpoint_file(
            job_id=UUID(job_id),
            relative_path=relative_path,
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
            console.print(f"[red]Failed to download checkpoint file:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(payload))
    else:
        console.print(f"[green]Downloaded checkpoint file[/green] {payload['local_path']}")


@checkpoint_app.command("download-all")
def download_all_checkpoints(
    job_id: str,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory to write manifest + files."),
    ] = None,
    json_mode: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        payload = JobsService(create_cli_context()).download_all_checkpoint_files(
            job_id=UUID(job_id),
            output_dir=output_dir,
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
            console.print(f"[red]Failed to download checkpoint bundle:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if json_mode:
        typer.echo(json.dumps(payload))
    else:
        console.print(
            "[green]Downloaded checkpoint bundle[/green] "
            f"{payload['downloaded_files']}/{payload['total_files']} files "
            f"to {payload['output_dir']}"
        )

    if payload.get("status") == "partial_failure":
        raise typer.Exit(code=1)
