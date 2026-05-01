from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.markup import escape

from relaymd.cli.context import create_cli_context
from relaymd.cli.services.workers_service import WorkersService

app = typer.Typer(help="List workers.")
console = Console()


def _render_workers_plain_lines(workers: list[dict[str, object]]) -> list[str]:
    lines = ["id\tplatform\tgpu_model\tvram_gb\tlast_heartbeat\tjobs_completed\tstatus"]
    for worker in workers:
        vram_gb = worker.get("vram_gb")
        jobs_completed = worker.get("jobs_completed")
        lines.append(
            "\t".join(
                [
                    str(worker.get("id") or "-"),
                    str(worker.get("platform") or "-"),
                    str(worker.get("gpu_model") or "-"),
                    "-" if vram_gb is None else str(vram_gb),
                    str(worker.get("last_heartbeat") or "-"),
                    "0" if jobs_completed is None else str(jobs_completed),
                    str(worker.get("status") or "unknown"),
                ]
            )
        )

    return lines


@app.command("list")
def list_workers(
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    try:
        workers = WorkersService(create_cli_context()).list_workers()
    except Exception as exc:  # noqa: BLE001
        if json_mode:
            typer.echo(json.dumps({"error": {"code": "list_failed", "message": str(exc)}}))
        else:
            console.print(f"[red]Failed to list workers:[/red] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    workers_payload = [worker.to_dict() for worker in workers]
    if json_mode:
        typer.echo(json.dumps({"workers": workers_payload}))
        return

    for line in _render_workers_plain_lines(workers_payload):
        typer.echo(line)
