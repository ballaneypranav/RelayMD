from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from relaymd_api_client.models.job_read import JobRead
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.submit_service import SubmitService

console = Console()


class SubmitCommandError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _emit_json_error(code: str, message: str) -> None:
    typer.echo(json.dumps({"error": {"code": code, "message": message}}))


def _exit_submit_error(*, json_mode: bool, code: str, message: str) -> NoReturn:
    if json_mode:
        _emit_json_error(code, message)
    else:
        console.print(message, markup=False)
    raise typer.Exit(code=1)


def ensure_worker_config(
    input_dir: Path,
    command: str | None,
    checkpoint_glob: str | None,
    checkpoint_poll_interval_seconds: int | None,
) -> None:
    worker_json = input_dir / "relaymd-worker.json"
    worker_toml = input_dir / "relaymd-worker.toml"

    if command is not None:
        if not checkpoint_glob:
            raise SubmitCommandError(
                code="missing_checkpoint_glob",
                message=(
                    "--command requires --checkpoint-glob so checkpoint uploads can be discovered."
                ),
            )
        worker_payload: dict[str, Any] = {
            "command": command,
            "checkpoint_glob_pattern": checkpoint_glob,
        }
        if checkpoint_poll_interval_seconds is not None:
            if checkpoint_poll_interval_seconds < 1:
                raise SubmitCommandError(
                    code="invalid_checkpoint_poll_interval",
                    message="--checkpoint-poll-interval-seconds value must be >= 1.",
                )
            worker_payload["checkpoint_poll_interval_seconds"] = checkpoint_poll_interval_seconds
        worker_json.write_text(f"{json.dumps(worker_payload, indent=2)}\n", encoding="utf-8")
        return

    if not worker_json.exists() and not worker_toml.exists():
        raise SubmitCommandError(
            code="missing_worker_config",
            message=(
                "Provide --command or add relaymd-worker.json / relaymd-worker.toml in the input "
                "directory."
            ),
        )


def validate_worker_config_inputs(
    input_dir: Path,
    command: str | None,
    checkpoint_glob: str | None,
    checkpoint_poll_interval_seconds: int | None,
) -> None:
    worker_json = input_dir / "relaymd-worker.json"
    worker_toml = input_dir / "relaymd-worker.toml"

    if command is not None:
        if not checkpoint_glob:
            raise SubmitCommandError(
                code="missing_checkpoint_glob",
                message=(
                    "--command requires --checkpoint-glob so checkpoint uploads can be discovered."
                ),
            )
        if checkpoint_poll_interval_seconds is not None and checkpoint_poll_interval_seconds < 1:
            raise SubmitCommandError(
                code="invalid_checkpoint_poll_interval",
                message="--checkpoint-poll-interval-seconds value must be >= 1.",
            )
        return

    if not worker_json.exists() and not worker_toml.exists():
        raise SubmitCommandError(
            code="missing_worker_config",
            message=(
                "Provide --command or add relaymd-worker.json / relaymd-worker.toml in the input "
                "directory."
            ),
        )


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


def register_job(
    job_id: uuid.UUID,
    title: str,
    b2_key: str,
    *,
    service: SubmitService | None = None,
) -> JobRead:
    submit_service = service or SubmitService(create_cli_context())
    return submit_service.register_job(job_id=job_id, title=title, b2_key=b2_key)


def submit(
    input_dir: Annotated[Path, typer.Argument(help="Input directory to pack and submit.")],
    title: Annotated[str, typer.Option("--title", help="Human-readable job title.")],
    command: Annotated[
        str | None,
        typer.Option("--command", help="Command to write to relaymd-worker.json."),
    ] = None,
    checkpoint_poll_interval_seconds: Annotated[
        int | None,
        typer.Option(
            "--checkpoint-poll-interval-seconds",
            help="Checkpoint poll interval to write alongside --command in relaymd-worker.json.",
        ),
    ] = None,
    checkpoint_glob: Annotated[
        str | None,
        typer.Option(
            "--checkpoint-glob",
            help="Checkpoint glob pattern to write alongside --command.",
        ),
    ] = None,
    json_mode: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    if not input_dir.exists() or not input_dir.is_dir():
        _exit_submit_error(
            json_mode=json_mode,
            code="invalid_input_dir",
            message=f"Input directory does not exist or is not a directory: {input_dir}",
        )

    job_id = uuid.uuid4()
    b2_key = f"jobs/{job_id}/input/bundle.tar.gz"

    try:
        validate_worker_config_inputs(
            input_dir=input_dir,
            command=command,
            checkpoint_glob=checkpoint_glob,
            checkpoint_poll_interval_seconds=checkpoint_poll_interval_seconds,
        )
    except SubmitCommandError as exc:
        _exit_submit_error(json_mode=json_mode, code=exc.code, message=exc.message)

    try:
        submit_service = SubmitService(create_cli_context())
    except Exception as exc:  # noqa: BLE001
        _exit_submit_error(
            json_mode=json_mode,
            code="missing_settings",
            message=f"Failed to load settings: {str(exc)}",
        )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            staged_input_dir = Path(tmpdir) / "input"
            shutil.copytree(input_dir, staged_input_dir)
            ensure_worker_config(
                staged_input_dir,
                command,
                checkpoint_glob,
                checkpoint_poll_interval_seconds,
            )

            archive_path = Path(tmpdir) / "bundle.tar.gz"
            create_bundle_archive(staged_input_dir, archive_path)
            if json_mode:
                submit_service.upload_bundle(local_archive=archive_path, b2_key=b2_key)
            else:
                upload_bundle(archive_path, b2_key, service=submit_service)
    except SubmitCommandError as exc:
        _exit_submit_error(json_mode=json_mode, code=exc.code, message=exc.message)
    except Exception as exc:  # noqa: BLE001
        _exit_submit_error(
            json_mode=json_mode,
            code="upload_failed",
            message=f"Failed to upload bundle: {str(exc)}",
        )

    try:
        created_job = register_job(job_id, title, b2_key, service=submit_service)
    except Exception as exc:  # noqa: BLE001
        _exit_submit_error(
            json_mode=json_mode,
            code="registration_failed",
            message=f"Failed to register job: {str(exc)}",
        )

    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "job_id": str(created_job.id),
                    "title": created_job.title,
                    "input_bundle_path": created_job.input_bundle_path,
                    "status": str(created_job.status.value),
                }
            )
        )
        return

    console.print(
        Panel.fit(
            f"[bold green]Job submitted[/bold green]\n[bold]{created_job.id}[/bold]",
            title="RelayMD",
        )
    )
