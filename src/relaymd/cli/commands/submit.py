from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.submit_service import SubmitService

console = Console()


def ensure_worker_config(input_dir: Path, command: str | None, checkpoint_glob: str | None) -> None:
    worker_json = input_dir / "relaymd-worker.json"
    worker_toml = input_dir / "relaymd-worker.toml"

    if command is not None:
        worker_payload: dict[str, Any] = {
            "command": command,
            "checkpoint_glob_pattern": checkpoint_glob,
        }
        worker_json.write_text(f"{json.dumps(worker_payload, indent=2)}\n", encoding="utf-8")
        return

    if not worker_json.exists() and not worker_toml.exists():
        console.print(
            "[red]Missing worker configuration:[/red] provide --command or add "
            "relaymd-worker.json / relaymd-worker.toml in the input directory."
        )
        raise typer.Exit(code=1)


def create_bundle_archive(input_dir: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sorted(input_dir.rglob("*")):
            if not path.is_file():
                continue
            arcname = path.relative_to(input_dir)
            tar.add(path, arcname=str(arcname))


def upload_bundle(
    local_archive: Path,
    b2_key: str,
    *,
    service: SubmitService | None = None,
) -> None:
    submit_service = service or SubmitService(create_cli_context())
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Uploading bundle to B2...", total=None)
        submit_service.upload_bundle(local_archive=local_archive, b2_key=b2_key)
        progress.update(task_id, description="Upload complete")


def register_job(title: str, b2_key: str, *, service: SubmitService | None = None) -> str:
    submit_service = service or SubmitService(create_cli_context())
    return submit_service.register_job(title=title, b2_key=b2_key)


def submit(
    input_dir: Annotated[Path, typer.Argument(help="Input directory to pack and submit.")],
    title: Annotated[str, typer.Option("--title", help="Human-readable job title.")],
    command: Annotated[
        str | None,
        typer.Option("--command", help="Command to write to relaymd-worker.json."),
    ] = None,
    checkpoint_glob: Annotated[
        str | None,
        typer.Option(
            "--checkpoint-glob",
            help="Checkpoint glob pattern to write alongside --command.",
        ),
    ] = None,
) -> None:
    if not input_dir.exists() or not input_dir.is_dir():
        console.print(
            f"[red]Input directory does not exist or is not a directory:[/red] {input_dir}"
        )
        raise typer.Exit(code=1)

    job_id = str(uuid.uuid4())
    b2_key = f"jobs/{job_id}/input/bundle.tar.gz"

    try:
        submit_service = SubmitService(create_cli_context())
        with tempfile.TemporaryDirectory() as tmpdir:
            staged_input_dir = Path(tmpdir) / "input"
            shutil.copytree(input_dir, staged_input_dir)
            ensure_worker_config(staged_input_dir, command, checkpoint_glob)

            archive_path = Path(tmpdir) / "bundle.tar.gz"
            create_bundle_archive(staged_input_dir, archive_path)
            upload_bundle(archive_path, b2_key, service=submit_service)

        created_job_id = register_job(title, b2_key, service=submit_service)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to submit job:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"[bold green]Job submitted[/bold green]\n[bold]{created_job_id}[/bold]",
            title="RelayMD",
        )
    )
