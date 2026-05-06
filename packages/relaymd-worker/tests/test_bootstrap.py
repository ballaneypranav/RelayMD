from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest
from relaymd.worker import bootstrap
from relaymd.worker.bootstrap import WorkerConfig


class _FakeSecret:
    def __init__(self, secret_value: str) -> None:
        self.secret_value = secret_value


class _FakeInfisicalClient:
    def __init__(self, settings, values: dict[str, str], should_fail: bool = False) -> None:
        self.settings = settings
        self.values = values
        self.should_fail = should_fail
        self.calls: list[tuple[str, str, str, str]] = []

    def getSecret(self, options) -> _FakeSecret:
        if self.should_fail:
            raise RuntimeError("unauthorized")
        self.calls.append(
            (
                options.secret_name,
                options.project_id,
                options.environment,
                options.path,
            )
        )
        try:
            return _FakeSecret(self.values[options.secret_name])
        except KeyError as exc:
            raise RuntimeError("secret not found") from exc


def test_run_bootstrap_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("HOSTNAME", "worker-a")

    joined = Mock()
    monkeypatch.setattr(bootstrap, "join_tailnet", joined)
    monkeypatch.setattr(bootstrap, "_wait_for_peer_reachable", Mock())

    values = {
        "AXIOM_TOKEN": "axiom-token",
        "B2_APPLICATION_KEY_ID": "key-id",
        "B2_APPLICATION_KEY": "key-secret",
        "B2_ENDPOINT": "https://s3.us-east-005.backblazeb2.com",
        "BUCKET_NAME": "relaymd-bucket",
        "DOWNLOAD_BEARER_TOKEN": "download-token",
        "TAILSCALE_AUTH_KEY": "tskey-ephemeral",
        "RELAYMD_API_TOKEN": "relay-token",
        "RELAYMD_ORCHESTRATOR_URL": "http://orchestrator.tail.ts.net:36158",
    }
    created_clients: list[_FakeInfisicalClient] = []

    def _build_client(*, settings) -> _FakeInfisicalClient:
        client = _FakeInfisicalClient(settings=settings, values=values)
        created_clients.append(client)
        return client

    monkeypatch.setattr(bootstrap, "InfisicalClient", _build_client)

    config = bootstrap.run_bootstrap()

    assert config == WorkerConfig(
        b2_application_key_id="key-id",
        b2_application_key="key-secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        purdue_s3_access_key="",
        purdue_s3_secret_key="",
        purdue_s3_endpoint="",
        purdue_s3_bucket_name="",
        purdue_s3_user="",
        download_bearer_token="download-token",
        tailscale_auth_key="tskey-ephemeral",
        relaymd_api_token="relay-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )
    client = created_clients[0]
    assert client.settings.client_id == "client-id"
    assert client.settings.client_secret == "client-secret"
    assert client.settings.site_url == "https://app.infisical.com"
    assert set(call[0] for call in client.calls) == {
        "AXIOM_TOKEN",
        "B2_APPLICATION_KEY_ID",
        "B2_APPLICATION_KEY",
        "B2_ENDPOINT",
        "BUCKET_NAME",
        "DOWNLOAD_BEARER_TOKEN",
        "TAILSCALE_AUTH_KEY",
        "RELAYMD_API_TOKEN",
        "RELAYMD_ORCHESTRATOR_URL",
        "PURDUE_S3_ACCESS_KEY",
        "PURDUE_S3_SECRET_KEY",
        "PURDUE_S3_ENDPOINT",
        "PURDUE_S3_BUCKET_NAME",
        "PURDUE_S3_USER",
    }
    joined.assert_called_once_with("tskey-ephemeral", "worker-a")


def test_run_bootstrap_missing_optional_download_bearer_token_uses_empty_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("HOSTNAME", "worker-a")
    monkeypatch.setattr(bootstrap, "join_tailnet", Mock())
    monkeypatch.setattr(bootstrap, "_wait_for_peer_reachable", Mock())

    values = {
        "AXIOM_TOKEN": "axiom-token",
        "B2_APPLICATION_KEY_ID": "key-id",
        "B2_APPLICATION_KEY": "key-secret",
        "B2_ENDPOINT": "https://s3.us-east-005.backblazeb2.com",
        "BUCKET_NAME": "relaymd-bucket",
        "TAILSCALE_AUTH_KEY": "tskey-ephemeral",
        "RELAYMD_API_TOKEN": "relay-token",
        "RELAYMD_ORCHESTRATOR_URL": "http://orchestrator.tail.ts.net:36158",
    }

    class _MissingOptionalClient(_FakeInfisicalClient):
        def getSecret(self, options) -> _FakeSecret:
            if options.secret_name == "DOWNLOAD_BEARER_TOKEN":
                raise RuntimeError("secret not found")
            return super().getSecret(options)

    def _build_client(*, settings) -> _MissingOptionalClient:
        return _MissingOptionalClient(settings=settings, values=values)

    monkeypatch.setattr(bootstrap, "InfisicalClient", _build_client)

    config = bootstrap.run_bootstrap()

    assert config.download_bearer_token == ""


def test_run_bootstrap_missing_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.setattr(bootstrap, "InfisicalClient", Mock(side_effect=AssertionError))

    with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is required"):
        bootstrap.run_bootstrap()


def test_run_bootstrap_malformed_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "missing-colon")
    monkeypatch.setattr(bootstrap, "InfisicalClient", Mock(side_effect=AssertionError))

    with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is malformed"):
        bootstrap.run_bootstrap()


def test_run_bootstrap_infisical_error_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setattr(bootstrap, "join_tailnet", Mock())

    def _build_failing_client(*, settings) -> _FakeInfisicalClient:
        return _FakeInfisicalClient(
            settings=settings,
            values={},
            should_fail=True,
        )

    monkeypatch.setattr(bootstrap, "InfisicalClient", _build_failing_client)

    with pytest.raises(RuntimeError, match="Failed to bootstrap worker from Infisical"):
        bootstrap.run_bootstrap()


def test_join_tailnet_runs_expected_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = "/tmp/relaymd-tailscale-test-runtime"
    monkeypatch.setenv("RELAYMD_TAILSCALE_RUNTIME_DIR", runtime_dir)
    monkeypatch.setenv("RELAYMD_TAILSCALE_SOCKS5_PORT", "20555")
    monkeypatch.delenv("RELAYMD_TAILSCALE_SOCKS5_LISTEN_ADDR", raising=False)
    monkeypatch.delenv("RELAYMD_TAILSCALE_SOCKS5_PROXY_URL", raising=False)

    popen_mock = Mock()
    popen_process = Mock()
    popen_process.poll.return_value = None
    popen_mock.return_value = popen_process
    monkeypatch.setattr(subprocess, "Popen", popen_mock)

    run_mock = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(subprocess, "run", run_mock)
    monkeypatch.setattr(bootstrap, "_wait_for_socks5_ready", Mock())
    monkeypatch.setattr(bootstrap, "_wait_for_tailscale_running", Mock())

    bootstrap.join_tailnet("ts-auth-key", "worker-host")

    popen_mock.assert_called_once_with(
        [
            "tailscaled",
            "--tun=userspace-networking",
            "--socks5-server=localhost:20555",
            f"--statedir={runtime_dir}/state",
            f"--socket={runtime_dir}/tailscaled.sock",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    run_mock.assert_called_once_with(
        [
            "tailscale",
            f"--socket={runtime_dir}/tailscaled.sock",
            "up",
            "--authkey=ts-auth-key",
            "--hostname=worker-host",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    bootstrap._cleanup_tailscale_runtime()


def test_wait_for_peer_reachable_retries_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    results = [
        subprocess.CompletedProcess(args=[], returncode=1, stdout="no reply", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="pong", stderr=""),
    ]

    def _run(args, **kwargs):
        _ = kwargs
        calls.append(args)
        return results.pop(0)

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)

    bootstrap._wait_for_peer_reachable(
        "relaymd-orchestrator",
        "/tmp/tailscaled.sock",
        timeout_seconds=30,
        ping_timeout_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert len(calls) == 2
    assert calls[0] == [
        "tailscale",
        "--socket=/tmp/tailscaled.sock",
        "ping",
        "--timeout=1s",
        "--c=1",
        "relaymd-orchestrator",
    ]


def test_wait_for_peer_reachable_raises_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        _ = (args, kwargs)
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="no reply", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(RuntimeError, match="Tailscale peer 'relaymd-orchestrator'"):
        bootstrap._wait_for_peer_reachable(
            "relaymd-orchestrator",
            "/tmp/tailscaled.sock",
            timeout_seconds=0.01,
            ping_timeout_seconds=1,
            poll_interval_seconds=0.01,
        )
