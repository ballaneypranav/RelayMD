from __future__ import annotations

import json
import os
import subprocess
import time
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
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "${INFISICAL_TOKEN:-}" "${RELAYMD_API_TOKEN:-}"\n',
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
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{_fake_readiness_json()}'\n",
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
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{_fake_readiness_json(ok=False)}'\n",
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
        'printf \'%s\\n\' \'{"overall":"healthy","healthy":1,"readiness_ok":1}\'\n',
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
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{_fake_readiness_json()}'\n",
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


# --- clean_scripts ---


def test_clean_scripts_deletes_old_sbatch_files(monkeypatch, tmp_path: Path) -> None:
    scripts_dir = tmp_path / "slurm"
    scripts_dir.mkdir()
    old_script = scripts_dir / "cluster-20240101T000000.000000Z-aabbccdd.sbatch"
    new_script = scripts_dir / "cluster-20990101T000000.000000Z-11223344.sbatch"
    old_script.write_text("#SBATCH", encoding="utf-8")
    new_script.write_text("#SBATCH", encoding="utf-8")
    old_time = time.time() - 40 * 86400
    os.utime(old_script, (old_time, old_time))

    monkeypatch.setenv("RELAYMD_LOG_DIRECTORY", str(tmp_path))
    service_cmd.clean_scripts(older_than=30, log_dir=None)

    assert not old_script.exists()
    assert new_script.exists()


def test_clean_scripts_respects_older_than_option(monkeypatch, tmp_path: Path) -> None:
    scripts_dir = tmp_path / "slurm"
    scripts_dir.mkdir()
    script = scripts_dir / "cluster-old.sbatch"
    script.write_text("#SBATCH", encoding="utf-8")
    recent_time = time.time() - 5 * 86400
    os.utime(script, (recent_time, recent_time))

    monkeypatch.setenv("RELAYMD_LOG_DIRECTORY", str(tmp_path))
    service_cmd.clean_scripts(older_than=30, log_dir=None)

    assert script.exists()


def test_clean_scripts_log_dir_option_overrides_env(monkeypatch, tmp_path: Path) -> None:
    scripts_dir = tmp_path / "slurm"
    scripts_dir.mkdir()
    old_script = scripts_dir / "cluster-old.sbatch"
    old_script.write_text("#SBATCH", encoding="utf-8")
    old_time = time.time() - 40 * 86400
    os.utime(old_script, (old_time, old_time))

    monkeypatch.delenv("RELAYMD_LOG_DIRECTORY", raising=False)
    service_cmd.clean_scripts(older_than=30, log_dir=str(tmp_path))

    assert not old_script.exists()


def test_clean_scripts_errors_when_log_dir_not_set(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RELAYMD_LOG_DIRECTORY", raising=False)
    monkeypatch.delenv("RELAYMD_DATA_ROOT", raising=False)
    monkeypatch.setenv("RELAYMD_CONFIG", str(tmp_path / "missing-relaymd-config.yaml"))
    with pytest.raises(typer.Exit) as exc:
        service_cmd.clean_scripts(older_than=30, log_dir=None)
    assert exc.value.exit_code == 1


def test_clean_scripts_no_op_when_slurm_dir_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RELAYMD_LOG_DIRECTORY", str(tmp_path))
    service_cmd.clean_scripts(older_than=30, log_dir=None)


# --- clean_logs ---


def test_clean_logs_truncates_wrapper_logs(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    log_dir = data_root / "logs" / "service"
    log_dir.mkdir(parents=True)
    orch_log = log_dir / "orchestrator-wrapper.log"
    proxy_log = log_dir / "proxy-wrapper.log"
    orch_log.write_text("lots of log content\n", encoding="utf-8")
    proxy_log.write_text("lots of log content\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(tmp_path / "apps"))

    service_cmd.clean_logs(service="all")

    assert orch_log.read_text(encoding="utf-8") == ""
    assert proxy_log.read_text(encoding="utf-8") == ""


def test_clean_logs_truncates_only_selected_service(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    log_dir = data_root / "logs" / "service"
    log_dir.mkdir(parents=True)
    orch_log = log_dir / "orchestrator-wrapper.log"
    proxy_log = log_dir / "proxy-wrapper.log"
    orch_log.write_text("orchestrator logs\n", encoding="utf-8")
    proxy_log.write_text("proxy logs\n", encoding="utf-8")
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(tmp_path / "apps"))

    service_cmd.clean_logs(service="orchestrator")

    assert orch_log.read_text(encoding="utf-8") == ""
    assert proxy_log.read_text(encoding="utf-8") == "proxy logs\n"


def test_clean_logs_skips_missing_log_file(monkeypatch, tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    log_dir = data_root / "logs" / "service"
    log_dir.mkdir(parents=True)
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(data_root))
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(tmp_path / "apps"))

    service_cmd.clean_logs(service="orchestrator")


# --- prune_releases ---


def test_prune_releases_removes_old_dirs(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    releases_dir = service_root / "releases"
    releases_dir.mkdir(parents=True)
    r1 = releases_dir / "0.1.10"
    r2 = releases_dir / "0.1.11"
    r3 = releases_dir / "0.1.12"
    for d in (r1, r2, r3):
        d.mkdir()
    t = time.time()
    os.utime(r1, (t - 200, t - 200))
    os.utime(r2, (t - 100, t - 100))
    os.utime(r3, (t, t))
    current = service_root / "current"
    current.symlink_to(r3)
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))

    service_cmd.prune_releases(keep=1)

    assert not r1.exists()
    assert not r2.exists()
    assert r3.exists()


def test_prune_releases_never_removes_current_target(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    releases_dir = service_root / "releases"
    releases_dir.mkdir(parents=True)
    r1 = releases_dir / "0.1.10"
    r2 = releases_dir / "0.1.11"
    for d in (r1, r2):
        d.mkdir()
    t = time.time()
    os.utime(r1, (t - 100, t - 100))
    os.utime(r2, (t, t))
    current = service_root / "current"
    current.symlink_to(r1)
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))

    service_cmd.prune_releases(keep=1)

    assert r1.exists()
    assert r2.exists()


def test_prune_releases_keeps_n_most_recent(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    releases_dir = service_root / "releases"
    releases_dir.mkdir(parents=True)
    releases = [releases_dir / f"0.1.{i}" for i in range(5)]
    t = time.time()
    for i, d in enumerate(releases):
        d.mkdir()
        os.utime(d, (t + i, t + i))
    current = service_root / "current"
    current.symlink_to(releases[-1])
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))

    service_cmd.prune_releases(keep=2)

    assert not releases[0].exists()
    assert not releases[1].exists()
    assert not releases[2].exists()
    assert releases[3].exists()
    assert releases[4].exists()


def test_prune_releases_no_op_when_dir_missing(monkeypatch, tmp_path: Path) -> None:
    service_root = tmp_path / "apps" / "relaymd"
    service_root.mkdir(parents=True)
    monkeypatch.setenv("RELAYMD_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("RELAYMD_DATA_ROOT", str(tmp_path / "data"))

    service_cmd.prune_releases(keep=3)
