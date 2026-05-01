from __future__ import annotations

import json

import typer

from relaymd.cli.runtime_paths import named_path

app = typer.Typer(help="Print RelayMD install and data paths.")

PathName = typer.Argument(
    ...,
    help="One of: data, config, logs, status, current, release, env, yaml.",
)


@app.callback(invoke_without_command=True)
def path(
    name: str = PathName,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Print a resolved RelayMD path."""
    try:
        resolved = named_path(name)
        if json_mode:
            typer.echo(json.dumps({"name": name, "path": str(resolved)}))
        else:
            typer.echo(str(resolved))
    except KeyError as exc:
        raise typer.BadParameter(
            "expected one of: data, config, logs, status, current, release, env, yaml"
        ) from exc
