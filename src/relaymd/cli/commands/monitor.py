from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import typer

from relaymd.cli.commands.jobs import _render_jobs_plain_lines
from relaymd.cli.commands.workers import _render_workers_plain_lines
from relaymd.cli.context import create_cli_context
from relaymd.cli.services.jobs_service import JobsService
from relaymd.cli.services.workers_service import WorkersService


def _build_monitor_snapshot_lines(
    *,
    updated_at: str,
    jobs: list[dict[str, Any]],
    workers: list[dict[str, object]],
) -> list[str]:
    return [
        f"updated_at\t{updated_at}",
        "",
        "[jobs]",
        *_render_jobs_plain_lines(jobs),
        "",
        "[workers]",
        *_render_workers_plain_lines(workers),
    ]


def monitor(
    interval_seconds: float = typer.Option(
        3.0,
        "--interval-seconds",
        min=0.1,
        help="Seconds between refreshes.",
    ),
) -> None:
    context = create_cli_context()
    jobs_service = JobsService(context)
    workers_service = WorkersService(context)

    try:
        while True:
            jobs = [job.to_dict() for job in jobs_service.list_jobs()]
            workers = [worker.to_dict() for worker in workers_service.list_workers()]
            updated_at = datetime.now(UTC).isoformat()

            # Render one snapshot per refresh; terminal clear keeps latest view on screen.
            typer.clear()
            for line in _build_monitor_snapshot_lines(
                updated_at=updated_at,
                jobs=jobs,
                workers=workers,
            ):
                typer.echo(line)

            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        return
