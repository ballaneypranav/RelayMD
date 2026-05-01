from __future__ import annotations

from typer.testing import CliRunner

from relaymd.cli import __version__
from relaymd.cli.__main__ import app


def test_cli_version_flag_prints_installed_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"relaymd {__version__}\n"
