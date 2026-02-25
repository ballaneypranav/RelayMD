from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock, call
from uuid import uuid4

import httpx
import pytest
from relaymd.worker.heartbeat import HeartbeatThread
from relaymd_api_client import errors as api_errors
from relaymd_api_client.models.http_validation_error import (
    HTTPValidationError as ApiHTTPValidationError,
)
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


def test_heartbeat_send_raises_on_validation_error_response(monkeypatch) -> None:
    send = Mock(return_value=ApiHTTPValidationError.from_dict({"detail": []}))
    monkeypatch.setattr(HEARTBEAT_SYNC_TARGET, send)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
    )

    with pytest.raises(RuntimeError):
        thread._send(client=cast(Any, object()))

    send.assert_called_once()
