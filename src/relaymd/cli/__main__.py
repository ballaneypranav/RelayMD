from __future__ import annotations

import os
import sys

import typer

from relaymd.cli.commands.jobs import app as jobs_app
from relaymd.cli.commands.monitor import monitor
from relaymd.cli.commands.submit import submit
from relaymd.cli.commands.workers import app as workers_app
from relaymd.dashboard_proxy import DashboardProxySettings, create_dashboard_proxy_app

app = typer.Typer(help="RelayMD operator CLI")
orchestrator_app = typer.Typer(help="Orchestrator commands")


@orchestrator_app.command()
def up(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(36158, help="Bind port"),
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
        uvicorn.run(
            "relaymd.orchestrator.main:create_app",
            host=host,
            port=port,
            factory=True,
        )
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("relaymd.orchestrator"):
            typer.echo(
                "relaymd dependencies are not installed. Run: uv sync",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        raise


@orchestrator_app.command("proxy")
def proxy(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(36159, help="Bind port"),
    upstream_url: str = typer.Option("http://127.0.0.1:36158", help="Upstream RelayMD URL"),
    username: str = typer.Option(
        default_factory=lambda: os.getenv("RELAYMD_DASHBOARD_USERNAME", ""),
        help="Dashboard basic-auth username. Defaults to RELAYMD_DASHBOARD_USERNAME.",
    ),
    password: str = typer.Option(
        default_factory=lambda: os.getenv("RELAYMD_DASHBOARD_PASSWORD", ""),
        help="Dashboard basic-auth password. Defaults to RELAYMD_DASHBOARD_PASSWORD.",
    ),
) -> None:
    """Start a basic-auth reverse proxy in front of the RelayMD dashboard."""
    if not username.strip():
        typer.echo(
            "Dashboard proxy username is required. Set --username or RELAYMD_DASHBOARD_USERNAME.",
            err=True,
        )
        raise typer.Exit(code=1)
    if not password.strip():
        typer.echo(
            "Dashboard proxy password is required. Set --password or RELAYMD_DASHBOARD_PASSWORD.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        typer.echo("relaymd dependencies are not installed. Run: uv sync", err=True)
        raise typer.Exit(code=1) from exc

    uvicorn.run(
        create_dashboard_proxy_app(
            DashboardProxySettings(
                upstream_url=upstream_url,
                username=username,
                password=password,
            )
        ),
        host=host,
        port=port,
    )


app.command()(submit)
app.command()(monitor)
app.add_typer(jobs_app, name="jobs")
app.add_typer(workers_app, name="workers")
app.add_typer(orchestrator_app, name="orchestrator")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main())
