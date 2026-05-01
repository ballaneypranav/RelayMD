from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from relaymd.cli import remote_dispatch
from relaymd.cli.runtime_paths import RelaymdPaths


def _paths(tmp_path: Path, *, primary_host: str = "") -> RelaymdPaths:
    data_root = tmp_path / "relaymd-service"
    return RelaymdPaths(
        service_root=tmp_path / "apps" / "relaymd",
        data_root=data_root,
        current_link=tmp_path / "apps" / "relaymd" / "current",
        config_dir=data_root / "config",
        yaml_config=data_root / "config" / "relaymd-config.yaml",
        env_file=data_root / "config" / "relaymd-service.env",
        status_file=data_root / "state" / "relaymd-service.status",
        service_log_dir=data_root / "logs" / "service",
        orchestrator_wrapper_log=data_root / "logs" / "service" / "orchestrator.log",
        proxy_wrapper_log=data_root / "logs" / "service" / "proxy.log",
        current_release=tmp_path / "apps" / "relaymd" / "current",
        releases_dir=tmp_path / "apps" / "relaymd" / "releases",
        orchestrator_session="relaymd-service",
        proxy_session="relaymd-service-proxy",
        orchestrator_port="36158",
        proxy_port="36159",
        primary_host=primary_host,
    )


def _write_status(
    paths: RelaymdPaths,
    *,
    host: str,
    active: bool = True,
    fresh: bool = True,
) -> None:
    timestamp = (
        datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if fresh
        else "2000-01-01T00:00:00Z"
    )
    active_value = "1" if active else "0"
    paths.status_file.parent.mkdir(parents=True)
    paths.status_file.write_text(
        "\n".join(
            [
                f"HOST={host}",
                f"ORCHESTRATOR_ACTIVE={active_value}",
                f"ORCHESTRATOR_HEARTBEAT_AT={timestamp}",
                f"PROXY_ACTIVE={active_value}",
                f"PROXY_HEARTBEAT_AT={timestamp}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_should_delegate_api_command_from_non_service_host(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host="gilbreth-fe01")

    target = remote_dispatch.should_delegate_to_remote_host(
        args=["submit", "input", "--json"],
        paths=paths,
        current_host_name="gilbreth-fe00",
    )

    assert target == "gilbreth-fe01"


def test_should_not_delegate_on_locked_host(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host="gilbreth-fe01")

    assert (
        remote_dispatch.should_delegate_to_remote_host(
            args=["jobs", "list"],
            paths=paths,
            current_host_name="gilbreth-fe01",
        )
        is None
    )


@pytest.mark.parametrize(
    ("args", "active", "fresh"),
    [
        (["status", "--json"], True, True),
        (["config", "show-paths"], True, True),
        (["path", "status"], True, True),
        (["submit", "--help"], True, True),
        (["workers", "list"], False, True),
        (["monitor"], True, False),
    ],
)
def test_should_not_delegate_excluded_inactive_or_stale_cases(
    tmp_path: Path,
    args: list[str],
    active: bool,
    fresh: bool,
) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host="gilbreth-fe01", active=active, fresh=fresh)

    assert (
        remote_dispatch.should_delegate_to_remote_host(
            args=args,
            paths=paths,
            current_host_name="gilbreth-fe00",
        )
        is None
    )


def test_should_not_delegate_with_recursion_guard(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host="gilbreth-fe01")

    assert (
        remote_dispatch.should_delegate_to_remote_host(
            args=["submit", "input"],
            paths=paths,
            current_host_name="gilbreth-fe00",
            env={remote_dispatch.REMOTE_DISPATCH_ENV: "1"},
        )
        is None
    )


@pytest.mark.parametrize("host", ["-oProxyCommand=sh", "bad host", "user@host", "host/path"])
def test_should_not_delegate_unsafe_ssh_destination(tmp_path: Path, host: str) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host=host)

    assert (
        remote_dispatch.should_delegate_to_remote_host(
            args=["submit", "input"],
            paths=paths,
            current_host_name="gilbreth-fe00",
        )
        is None
    )


def test_build_remote_dispatch_target_rejects_unsafe_ssh_destination(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsafe SSH destination"):
        remote_dispatch.build_remote_dispatch_target(
            argv=["relaymd", "submit", "input"],
            target_host="-oProxyCommand=sh",
            cwd=tmp_path,
        )


def test_build_remote_dispatch_target_quotes_cwd_executable_and_args(tmp_path: Path) -> None:
    executable = tmp_path / "relaymd"
    executable.touch()
    cwd = tmp_path / "project with spaces"
    cwd.mkdir()

    target = remote_dispatch.build_remote_dispatch_target(
        argv=[str(executable), "submit", "input dir", "--title", "a job", "--json"],
        target_host="gilbreth-fe01",
        cwd=cwd,
    )

    assert target.command[0:3] == ["ssh", "--", "gilbreth-fe01"]
    assert "cd" in target.remote_command
    assert "project with spaces" in target.remote_command
    assert f"{remote_dispatch.REMOTE_DISPATCH_ENV}=1" in target.remote_command
    assert "'input dir'" in target.remote_command
    assert "'a job'" in target.remote_command
    assert "--json" in target.remote_command


def test_maybe_dispatch_runs_ssh_and_exits_with_remote_code(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write_status(paths, host="gilbreth-fe01")
    run = Mock(return_value=subprocess.CompletedProcess(["ssh"], 42))
    monkeypatch.setattr(remote_dispatch, "resolve_paths", lambda: paths)
    monkeypatch.setattr(remote_dispatch, "current_host", lambda: "gilbreth-fe00")
    monkeypatch.setattr(remote_dispatch.subprocess, "run", run)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        remote_dispatch.maybe_dispatch_from_argv(["relaymd", "submit", "input", "--json"])

    assert exc.value.code == 42
    command = run.call_args.args[0]
    assert command[0:3] == ["ssh", "--", "gilbreth-fe01"]
    assert command[3].endswith("relaymd submit input --json")
