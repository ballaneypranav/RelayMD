from __future__ import annotations

import typer

from relaymd.cli.runtime_paths import named_path

app = typer.Typer(help="Print RelayMD install and data paths.")

PathName = typer.Argument(
    ...,
    help="One of: data, config, logs, status, current, release, env, yaml.",
)


@app.callback(invoke_without_command=True)
def path(name: str = PathName) -> None:
    """Print a resolved RelayMD path."""
    try:
        typer.echo(str(named_path(name)))
    except KeyError as exc:
        raise typer.BadParameter(
            "expected one of: data, config, logs, status, current, release, env, yaml"
        ) from exc
