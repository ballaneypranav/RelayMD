from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import typer

from relaymd.cli.commands import service as service_cmd


def test_up_runs_orchestrator_then_proxy_wrappers(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    bin_dir = service_root / "bin"
    bin_dir.mkdir(parents=True)
    up_script = bin_dir / "relaymd-service-up"
    proxy_script = bin_dir / "relaymd-service-proxy"
    up_script.touch()
    proxy_script.touch()
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))
    run = Mock()
    monkeypatch.setattr(service_cmd.subprocess, "run", run)

    service_cmd.up(force=True)

    assert [call.args[0] for call in run.call_args_list] == [
        [str(up_script), "--force"],
        [str(proxy_script), "--force"],
    ]


def test_status_delegates_to_status_wrapper_with_flags(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    bin_dir = service_root / "bin"
    bin_dir.mkdir(parents=True)
    status_script = bin_dir / "relaymd-service-status"
    status_script.touch()
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))
    run = Mock()
    monkeypatch.setattr(service_cmd.subprocess, "run", run)

    service_cmd.status(verbose=True, json_mode=True, no_color=True)

    run.assert_called_once_with(
        [str(status_script), "--verbose", "--json", "--no-color"],
        check=True,
    )


def test_down_kills_sessions_and_marks_status_inactive(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    status_file.write_text(
        "HOST=testhost\nORCHESTRATOR_ACTIVE=1\nPROXY_ACTIVE=1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(service_cmd, "_current_host", lambda: "testhost")
    run = Mock()
    monkeypatch.setattr(service_cmd.subprocess, "run", run)

    service_cmd.down()

    commands = [call.args[0] for call in run.call_args_list]
    assert ["tmux", "kill-session", "-t", "relaymd-service-proxy"] in commands
    assert ["tmux", "kill-session", "-t", "relaymd-service"] in commands
    status_text = status_file.read_text(encoding="utf-8")
    assert "ORCHESTRATOR_ACTIVE=0\n" in status_text
    assert "PROXY_ACTIVE=0\n" in status_text


def test_down_exits_cleanly_when_tmux_is_missing(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    status_file.write_text("HOST=testhost\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setattr(service_cmd, "_current_host", lambda: "testhost")
    monkeypatch.setattr(
        service_cmd.subprocess,
        "run",
        Mock(side_effect=FileNotFoundError("tmux")),
    )

    with pytest.raises(typer.Exit) as exc:
        service_cmd.down()

    assert exc.value.exit_code == 127
