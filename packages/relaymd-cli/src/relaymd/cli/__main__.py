from __future__ import annotations

import sys

import typer
from relaymd.cli.commands.jobs import app as jobs_app
from relaymd.cli.commands.submit import submit
from relaymd.cli.commands.workers import app as workers_app

cli = typer.Typer(help="RelayMD operator CLI")
cli.command()(submit)
cli.add_typer(jobs_app, name="jobs")
cli.add_typer(workers_app, name="workers")


def app() -> None:
    cli()


if __name__ == "__main__":
    sys.exit(app())
