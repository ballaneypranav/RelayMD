from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, call
from uuid import uuid4

import httpx
import pytest
from relaymd.worker.heartbeat import HeartbeatThread
from relaymd.worker.main import _handle_sigterm
from relaymd_api_client import errors as api_errors
from tenacity import wait_none

HEARTBEAT_SYNC_TARGET = (
    "relaymd.worker.heartbeat."
    "heartbeat_worker_workers_worker_id_heartbeat_post.sync"
)


class _FakeApiClient:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False


def _disable_send_retry_wait() -> None:
    # tenacity attaches retry metadata dynamically; cast for static type checking.
    send_with_retry_any = cast(Any, HeartbeatThread._send)
    send_with_retry_any.retry.wait = wait_none()
    send_with_retry_any.retry.sleep = lambda _: None


def test_heartbeat_fires_at_expected_interval(monkeypatch) -> None:
    _disable_send_retry_wait()

    stop_event = Mock()
    stop_event.is_set.return_value = False
    stop_event.wait.side_effect = [False, True]

    send = Mock(return_value=None)
    monkeypatch.setattr("relaymd.worker.heartbeat.RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        interval_seconds=7,
        stop_event=stop_event,
    )
    thread.run()

    assert stop_event.wait.call_args_list == [call(7), call(7)]
    assert send.call_count == 2


def test_heartbeat_http_failure_logs_warning_and_continues(monkeypatch) -> None:
    _disable_send_retry_wait()

    stop_event = Mock()
    stop_event.is_set.return_value = False
    stop_event.wait.side_effect = [False, True]

    send = Mock(side_effect=httpx.HTTPError("heartbeat failed"))
    monkeypatch.setattr("relaymd.worker.heartbeat.RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)
    warning = Mock()
    monkeypatch.setattr("relaymd.worker.heartbeat.LOG.warning", warning)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    assert warning.call_count == 2
    assert send.call_count == 6


def test_heartbeat_retries_on_transient_failure_then_succeeds(monkeypatch) -> None:
    _disable_send_retry_wait()

    stop_event = Mock()
    stop_event.is_set.return_value = False
    stop_event.wait.side_effect = [True]

    send = Mock(side_effect=[httpx.HTTPError("temporary outage"), None])
    monkeypatch.setattr("relaymd.worker.heartbeat.RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)
    warning = Mock()
    monkeypatch.setattr("relaymd.worker.heartbeat.LOG.warning", warning)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    assert send.call_count == 2
    warning.assert_not_called()


def test_heartbeat_unexpected_status_logs_warning_and_continues(monkeypatch) -> None:
    _disable_send_retry_wait()

    stop_event = Mock()
    stop_event.is_set.return_value = False
    stop_event.wait.side_effect = [False, True]

    send = Mock(side_effect=api_errors.UnexpectedStatus(500, b"error"))
    monkeypatch.setattr("relaymd.worker.heartbeat.RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)
    warning = Mock()
    monkeypatch.setattr("relaymd.worker.heartbeat.LOG.warning", warning)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    assert warning.call_count == 2


def test_heartbeat_stops_when_stop_event_is_set(monkeypatch) -> None:
    stop_event = Mock()
    stop_event.is_set.return_value = True

    send = Mock(return_value=None)
    monkeypatch.setattr("relaymd.worker.heartbeat.RelaymdApiClient", lambda **_: _FakeApiClient())
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    send.assert_not_called()


def test_sigterm_triggers_checkpoint_upload_deregister_and_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    job_id = uuid4()
    worker_id = uuid4()
    checkpoint = tmp_path / "final.chk"
    checkpoint.write_bytes(b"checkpoint-data")

    process = Mock()
    storage = Mock()
    stop_event = Mock()
    heartbeat_thread = Mock()

    api_client = cast(Any, object())
    checkpoint_sync = Mock(return_value=None)
    deregister_sync = Mock(return_value=None)
    monkeypatch.setattr(
        "relaymd.worker.main.report_checkpoint_jobs_job_id_checkpoint_post.sync",
        checkpoint_sync,
    )
    monkeypatch.setattr(
        "relaymd.worker.main.deregister_worker_workers_worker_id_deregister_post.sync",
        deregister_sync,
    )

    wait_for_checkpoint = Mock(return_value=checkpoint)
    monkeypatch.setattr("relaymd.worker.main._wait_for_final_checkpoint", wait_for_checkpoint)

    with pytest.raises(SystemExit) as excinfo:
        _handle_sigterm(
            process=process,
            workdir=tmp_path,
            checkpoint_glob_pattern="*.chk",
            checkpoint_b2_key=f"jobs/{job_id}/checkpoints/latest",
            storage=storage,
            client=api_client,
            api_token="token",
            job_id=job_id,
            worker_id=worker_id,
            stop_event=stop_event,
            heartbeat_thread=heartbeat_thread,
            log=Mock(),
        )

    assert excinfo.value.code == 0
    process.terminate.assert_called_once_with()
    wait_for_checkpoint.assert_called_once_with(tmp_path, "*.chk")
    storage.upload_file.assert_called_once_with(checkpoint, f"jobs/{job_id}/checkpoints/latest")
    checkpoint_sync.assert_called_once()
    deregister_sync.assert_called_once()
    stop_event.set.assert_called_once_with()
    heartbeat_thread.join.assert_called_once_with(timeout=5)
