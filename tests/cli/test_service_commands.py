from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
import typer

from relaymd.cli.commands import service as service_cmd


def _fake_readiness_json(*, ok: bool = True) -> str:
    payload = {
        "_ok": ok,
        "config": {"ok": True},
        "secrets": {"ok": ok, **({} if ok else {"error": "missing"})},
        "release": {"ok": True},
        "proxy_auth": {"ok": True},
        "scheduler": {"ok": True},
        "cli_submit": {"ok": True},
        "network": {"ok": True},
    }
    return json.dumps(payload, separators=(",", ":"))


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


def test_hpc_cli_wrapper_sources_service_env_before_exec(tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    data_root = tmp_path / "data" / "relaymd-service"
    current = service_root / "current"
    current.mkdir(parents=True)
    env_file = data_root / "config" / "relaymd-service.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        'INFISICAL_TOKEN="client:secret"\nRELAYMD_API_TOKEN="api-token"\n',
        encoding="utf-8",
    )
    cli_bin = current / "relaymd"
    cli_bin.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"${INFISICAL_TOKEN:-}\" \"${RELAYMD_API_TOKEN:-}\"\n",
        encoding="utf-8",
    )
    cli_bin.chmod(0o755)
    wrapper = Path("deploy/hpc/relaymd").resolve()

    result = subprocess.run(
        [str(wrapper), "submit", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_SERVICE_ROOT": str(service_root),
            "RELAYMD_DATA_ROOT": str(data_root),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["client:secret", "api-token"]


def test_hpc_cli_wrapper_uses_current_link_from_service_env(tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    data_root = tmp_path / "data" / "relaymd-service"
    default_current = service_root / "current"
    override_current = service_root / "override-current"
    default_current.mkdir(parents=True)
    override_current.mkdir(parents=True)
    env_file = data_root / "config" / "relaymd-service.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(f'CURRENT_LINK="{override_current}"\n', encoding="utf-8")
    (default_current / "relaymd").write_text(
        "#!/usr/bin/env bash\nprintf 'default\\n'\n",
        encoding="utf-8",
    )
    (override_current / "relaymd").write_text(
        "#!/usr/bin/env bash\nprintf 'override\\n'\n",
        encoding="utf-8",
    )
    (default_current / "relaymd").chmod(0o755)
    (override_current / "relaymd").chmod(0o755)
    wrapper = Path("deploy/hpc/relaymd").resolve()

    result = subprocess.run(
        [str(wrapper), "--version"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_SERVICE_ROOT": str(service_root),
            "RELAYMD_DATA_ROOT": str(data_root),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    assert result.stdout == "override\n"


def test_status_wrapper_json_reports_remote_healthy_when_heartbeat_is_fresh(
    tmp_path: Path,
) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    data_root = tmp_path / "relaymd-service"
    current = service_root / "current"
    current.mkdir(parents=True)
    cli = current / "relaymd"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' '{_fake_readiness_json()}'\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    heartbeat = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_file.write_text(
        "\n".join(
            [
                "HOST=relaymd-remote-test-host",
                "ORCHESTRATOR_ACTIVE=1",
                f"ORCHESTRATOR_HEARTBEAT_AT={heartbeat}",
                "PROXY_ACTIVE=1",
                f"PROXY_HEARTBEAT_AT={heartbeat}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    script = Path("deploy/hpc/relaymd-service-status").resolve()

    result = subprocess.run(
        [str(script), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_SERVICE_ROOT": str(service_root),
            "RELAYMD_DATA_ROOT": str(data_root),
            "CURRENT_LINK": str(current),
            "RELAYMD_STATUS_FILE": str(status_file),
            "RELAYMD_PRIMARY_HOST": "relaymd-remote-test-host",
            "RELAYMD_STATUS_REMOTE_CHECK": "1",
            "RELAYMD_STATUS_REQUEST_HOST": "relaymd-local-test-host",
            "RELAYMD_HEARTBEAT_STALE_SECONDS": "99999999999",
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["overall"] == "healthy"
    assert payload["healthy"] == 1
    assert payload["access_mode"] == "ssh_delegated"
    assert payload["readiness_ok"] == 1
    assert payload["readiness"]["_ok"] is True


def test_status_wrapper_json_reports_readiness_blocks(tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    data_root = tmp_path / "relaymd-service"
    current = service_root / "current"
    current.mkdir(parents=True)
    cli = current / "relaymd"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' '{_fake_readiness_json(ok=False)}'\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    heartbeat = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_file.write_text(
        "\n".join(
            [
                "HOST=relaymd-local-test-host",
                "ORCHESTRATOR_ACTIVE=1",
                f"ORCHESTRATOR_HEARTBEAT_AT={heartbeat}",
                "PROXY_ACTIVE=1",
                f"PROXY_HEARTBEAT_AT={heartbeat}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    script = Path("deploy/hpc/relaymd-service-status").resolve()

    result = subprocess.run(
        [str(script), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_SERVICE_ROOT": str(service_root),
            "RELAYMD_DATA_ROOT": str(data_root),
            "CURRENT_LINK": str(current),
            "RELAYMD_STATUS_FILE": str(status_file),
            "RELAYMD_PRIMARY_HOST": "relaymd-local-test-host",
            "RELAYMD_STATUS_REMOTE_CHECK": "1",
            "RELAYMD_STATUS_REQUEST_HOST": "relaymd-local-test-host",
            "RELAYMD_HEARTBEAT_STALE_SECONDS": "99999999999",
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["readiness_ok"] == 0
    assert payload["readiness"]["secrets"]["ok"] is False


def test_status_wrapper_sshes_to_expected_host_for_off_host_status(tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    heartbeat = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_file.write_text(
        "\n".join(
            [
                "HOST=relaymd-remote-test-host",
                "ORCHESTRATOR_ACTIVE=1",
                f"ORCHESTRATOR_HEARTBEAT_AT={heartbeat}",
                "PROXY_ACTIVE=1",
                f"PROXY_HEARTBEAT_AT={heartbeat}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$@\" > {log_path}\n"
        "printf '%s\\n' '************************************************************'\n"
        "printf '%s\\n' '***** Use of Purdue BoilerKey or SSH keys is Required ******'\n"
        "printf '%s\\n' '************************************************************'\n"
        "printf '%s\\n' '{\"overall\":\"healthy\",\"healthy\":1,\"readiness_ok\":1}'\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    script = Path("deploy/hpc/relaymd-service-status").resolve()

    result = subprocess.run(
        [str(script), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_DATA_ROOT": str(data_root),
            "RELAYMD_STATUS_FILE": str(status_file),
            "RELAYMD_PRIMARY_HOST": "relaymd-remote-test-host",
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
        },
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["healthy"] == 1
    assert "BoilerKey" not in result.stdout
    assert "relaymd-remote-test-host" in log_path.read_text(encoding="utf-8")
    assert "RELAYMD_STATUS_REMOTE_CHECK=1" in log_path.read_text(encoding="utf-8")


def test_status_wrapper_json_reports_ssh_failure(tmp_path: Path) -> None:
    data_root = tmp_path / "relaymd-service"
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    status_file.write_text(
        "HOST=relaymd-remote-test-host\nORCHESTRATOR_ACTIVE=1\nPROXY_ACTIVE=1\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\nprintf 'ssh unavailable\\n' >&2\nexit 255\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    script = Path("deploy/hpc/relaymd-service-status").resolve()

    result = subprocess.run(
        [str(script), "--json"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_DATA_ROOT": str(data_root),
            "RELAYMD_STATUS_FILE": str(status_file),
            "RELAYMD_PRIMARY_HOST": "relaymd-remote-test-host",
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
        },
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["remote_check"]["ok"] is False
    assert payload["readiness"]["remote_check"]["ok"] is False


def test_status_wrapper_human_output_includes_readiness_lines(tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    data_root = tmp_path / "relaymd-service"
    current = service_root / "current"
    current.mkdir(parents=True)
    cli = current / "relaymd"
    cli.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' '{_fake_readiness_json()}'\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    status_file = data_root / "state" / "relaymd-service.status"
    status_file.parent.mkdir(parents=True)
    heartbeat = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    status_file.write_text(
        "\n".join(
            [
                "HOST=relaymd-local-test-host",
                "ORCHESTRATOR_ACTIVE=1",
                f"ORCHESTRATOR_HEARTBEAT_AT={heartbeat}",
                "PROXY_ACTIVE=1",
                f"PROXY_HEARTBEAT_AT={heartbeat}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    script = Path("deploy/hpc/relaymd-service-status").resolve()

    result = subprocess.run(
        [str(script), "--no-color"],
        check=False,
        capture_output=True,
        text=True,
        env={
            "RELAYMD_SERVICE_ROOT": str(service_root),
            "RELAYMD_DATA_ROOT": str(data_root),
            "CURRENT_LINK": str(current),
            "RELAYMD_STATUS_FILE": str(status_file),
            "RELAYMD_PRIMARY_HOST": "relaymd-local-test-host",
            "RELAYMD_STATUS_REMOTE_CHECK": "1",
            "RELAYMD_STATUS_REQUEST_HOST": "relaymd-local-test-host",
            "RELAYMD_HEARTBEAT_STALE_SECONDS": "99999999999",
            "PATH": "/usr/bin:/bin",
        },
    )

    assert "Readiness:" in result.stdout
    assert "Secrets: OK" in result.stdout
    assert "Storage: OK" in result.stdout


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
