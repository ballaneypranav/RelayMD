from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, call
from uuid import uuid4

import httpx
import pytest
from relaymd.worker.heartbeat import HeartbeatThread
from relaymd.worker.main import _handle_sigterm


def _client_cm(client: Mock) -> Mock:
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=client)
    context_manager.__exit__ = Mock(return_value=False)
    return context_manager


def test_heartbeat_fires_at_expected_interval(monkeypatch) -> None:
    stop_event = Mock()
    stop_event.wait.side_effect = [False, True]

    response = Mock()
    response.raise_for_status.return_value = None
    client = Mock()
    client.post.return_value = response
    monkeypatch.setattr(
        "relaymd.worker.heartbeat.httpx.Client",
        lambda *args, **kwargs: _client_cm(client),
    )

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        interval_seconds=7,
        stop_event=stop_event,
    )
    thread.run()

    assert stop_event.wait.call_args_list == [call(7), call(7)]
    client.post.assert_called_once()


def test_heartbeat_http_failure_logs_warning_and_continues(monkeypatch) -> None:
    stop_event = Mock()
    stop_event.wait.side_effect = [False, True]

    client = Mock()
    client.post.side_effect = httpx.HTTPError("heartbeat failed")
    monkeypatch.setattr(
        "relaymd.worker.heartbeat.httpx.Client",
        lambda *args, **kwargs: _client_cm(client),
    )
    warning = Mock()
    monkeypatch.setattr("relaymd.worker.heartbeat.LOGGER.warning", warning)

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    warning.assert_called_once()


def test_heartbeat_stops_when_stop_event_is_set(monkeypatch) -> None:
    stop_event = Mock()
    stop_event.wait.return_value = True

    client = Mock()
    monkeypatch.setattr(
        "relaymd.worker.heartbeat.httpx.Client",
        lambda *args, **kwargs: _client_cm(client),
    )

    thread = HeartbeatThread(
        orchestrator_url="http://orchestrator",
        worker_id=uuid4(),
        api_token="token",
        stop_event=stop_event,
    )
    thread.run()

    client.post.assert_not_called()


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

    checkpoint_response = Mock()
    checkpoint_response.raise_for_status.return_value = None
    deregister_response = Mock()
    deregister_response.raise_for_status.return_value = None
    client = Mock()
    client.post.side_effect = [checkpoint_response, deregister_response]

    wait_for_checkpoint = Mock(return_value=checkpoint)
    monkeypatch.setattr("relaymd.worker.main._wait_for_final_checkpoint", wait_for_checkpoint)

    with pytest.raises(SystemExit) as excinfo:
        _handle_sigterm(
            process=process,
            workdir=tmp_path,
            checkpoint_glob_pattern="*.chk",
            checkpoint_b2_key=f"jobs/{job_id}/checkpoints/latest",
            storage=storage,
            client=client,
            job_id=job_id,
            worker_id=worker_id,
            stop_event=stop_event,
            heartbeat_thread=heartbeat_thread,
        )

    assert excinfo.value.code == 0
    process.terminate.assert_called_once_with()
    wait_for_checkpoint.assert_called_once_with(tmp_path, "*.chk")
    storage.upload_file.assert_called_once_with(checkpoint, f"jobs/{job_id}/checkpoints/latest")
    assert [c.args[0] for c in client.post.call_args_list] == [
        f"/jobs/{job_id}/checkpoint",
        f"/workers/{worker_id}/deregister",
    ]
    stop_event.set.assert_called_once_with()
    heartbeat_thread.join.assert_called_once_with(timeout=5)
