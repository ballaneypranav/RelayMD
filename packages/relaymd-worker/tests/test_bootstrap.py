from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pytest
import respx
from httpx import Response
from relaymd.worker import bootstrap
from relaymd.worker.bootstrap import WorkerConfig


def _secret_response(value: str) -> Response:
    return Response(200, json={"secret": {"secretValue": value}})


def test_run_bootstrap_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setenv("HOSTNAME", "worker-a")

    joined = Mock()
    monkeypatch.setattr(bootstrap, "join_tailnet", joined)

    with respx.mock(assert_all_called=True) as router:
        router.post(
            "https://app.infisical.com/api/v1/auth/universal-auth/login"
        ).mock(return_value=Response(200, json={"accessToken": "access-token"}))

        router.get(
            "https://app.infisical.com/api/v3/secrets/raw/B2_APPLICATION_KEY_ID"
        ).mock(return_value=_secret_response("key-id"))
        router.get("https://app.infisical.com/api/v3/secrets/raw/B2_APPLICATION_KEY").mock(
            return_value=_secret_response("key-secret")
        )
        router.get("https://app.infisical.com/api/v3/secrets/raw/B2_ENDPOINT").mock(
            return_value=_secret_response("https://s3.us-east-005.backblazeb2.com")
        )
        router.get("https://app.infisical.com/api/v3/secrets/raw/BUCKET_NAME").mock(
            return_value=_secret_response("relaymd-bucket")
        )
        router.get("https://app.infisical.com/api/v3/secrets/raw/TAILSCALE_AUTH_KEY").mock(
            return_value=_secret_response("tskey-ephemeral")
        )
        router.get("https://app.infisical.com/api/v3/secrets/raw/RELAYMD_API_TOKEN").mock(
            return_value=_secret_response("relay-token")
        )
        router.get(
            "https://app.infisical.com/api/v3/secrets/raw/RELAYMD_ORCHESTRATOR_URL"
        ).mock(return_value=_secret_response("http://orchestrator.tail.ts.net:8000"))

        config = bootstrap.run_bootstrap()

    assert config == WorkerConfig(
        b2_application_key_id="key-id",
        b2_application_key="key-secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        tailscale_auth_key="tskey-ephemeral",
        relaymd_api_token="relay-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:8000",
    )
    joined.assert_called_once_with("tskey-ephemeral", "worker-a")


def test_run_bootstrap_missing_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)

    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is required"):
            bootstrap.run_bootstrap()
        assert len(router.calls) == 0


def test_run_bootstrap_malformed_token_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "missing-colon")

    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(RuntimeError, match="INFISICAL_TOKEN is malformed"):
            bootstrap.run_bootstrap()
        assert len(router.calls) == 0


def test_run_bootstrap_infisical_error_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFISICAL_TOKEN", "client-id:client-secret")
    monkeypatch.setattr(bootstrap, "join_tailnet", Mock())

    with respx.mock(assert_all_called=True) as router:
        router.post(
            "https://app.infisical.com/api/v1/auth/universal-auth/login"
        ).mock(return_value=Response(401, json={"message": "unauthorized"}))

        with pytest.raises(RuntimeError, match="Failed to bootstrap worker from Infisical"):
            bootstrap.run_bootstrap()


def test_join_tailnet_runs_expected_subprocesses(monkeypatch: pytest.MonkeyPatch) -> None:
    popen_mock = Mock()
    popen_process = Mock()
    popen_process.poll.return_value = None
    popen_mock.return_value = popen_process
    monkeypatch.setattr(subprocess, "Popen", popen_mock)

    run_mock = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(subprocess, "run", run_mock)

    bootstrap.join_tailnet("ts-auth-key", "worker-host")

    popen_mock.assert_called_once_with(
        [
            "tailscaled",
            "--tun=userspace-networking",
            "--statedir=/tmp/tailscale-state",
            "--socket=/tmp/tailscaled.sock",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    run_mock.assert_called_once_with(
        [
            "tailscale",
            "--socket=/tmp/tailscaled.sock",
            "up",
            "--authkey=ts-auth-key",
            "--hostname=worker-host",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
