from __future__ import annotations

import sys

import typer

from relaymd.cli.commands.jobs import app as jobs_app
from relaymd.cli.commands.monitor import monitor
from relaymd.cli.commands.submit import submit
from relaymd.cli.commands.workers import app as workers_app

app = typer.Typer(help="RelayMD operator CLI")
orchestrator_app = typer.Typer(help="Orchestrator commands")


@orchestrator_app.command()
def up(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
) -> None:
    """Start the RelayMD orchestrator."""
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        typer.echo(
            "relaymd dependencies are not installed. Run: uv sync",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        uvicorn.run("relaymd.orchestrator.main:app", host=host, port=port)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("relaymd.orchestrator"):
            typer.echo(
                "relaymd dependencies are not installed. Run: uv sync",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        raise


app.command()(submit)
app.command()(monitor)
app.add_typer(jobs_app, name="jobs")
app.add_typer(workers_app, name="workers")
app.add_typer(orchestrator_app, name="orchestrator")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main())
