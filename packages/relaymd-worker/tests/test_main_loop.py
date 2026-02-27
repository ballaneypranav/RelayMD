from __future__ import annotations

import io
import signal
import tarfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock
from uuid import uuid4

import pytest
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.context import WorkerContext
from relaymd.worker.main import (
    BundleExecutionConfig,
    _build_storage_client,
    _run_assigned_job,
    run_worker,
)
from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable


def _write_bundle_tar(local_path: Path) -> None:
    bundle_config = b'{"command": ["md-engine", "--run"], "checkpoint_glob_pattern": "*.chk"}'
    checkpoint_bytes = b"checkpoint-data"

    with tarfile.open(local_path, "w:gz") as archive:
        config_info = tarfile.TarInfo("relaymd-worker.json")
        config_info.size = len(bundle_config)
        archive.addfile(config_info, io.BytesIO(bundle_config))

        checkpoint_info = tarfile.TarInfo("step_0001.chk")
        checkpoint_info.size = len(checkpoint_bytes)
        archive.addfile(checkpoint_info, io.BytesIO(checkpoint_bytes))


def test_build_storage_client_prefers_download_bearer_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_storage_client(**kwargs):
        captured.update(kwargs)
        return Mock()

    monkeypatch.setattr("relaymd.worker.main.StorageClient", fake_storage_client)

    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        download_bearer_token="download-token",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:8000",
    )
    runtime_settings = SimpleNamespace(
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )

    _build_storage_client(config, runtime_settings)

    assert captured["cf_bearer_token"] == "download-token"


def test_build_storage_client_fallbacks_to_runtime_then_api_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_storage_client(**kwargs):
        captured.update(kwargs)
        return Mock()

    monkeypatch.setattr("relaymd.worker.main.StorageClient", fake_storage_client)

    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        download_bearer_token="",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:8000",
    )

    runtime_settings = SimpleNamespace(
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )
    _build_storage_client(config, runtime_settings)
    assert captured["cf_bearer_token"] == "runtime-token"

    runtime_settings = SimpleNamespace(
        cf_worker_url="https://cf.example",
        cf_bearer_token="",
    )
    _build_storage_client(config, runtime_settings)
    assert captured["cf_bearer_token"] == "api-token"


def test_run_worker_full_cycle_with_assignment_then_no_job(monkeypatch) -> None:
    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:8000",
    )

    storage = Mock()

    def download_side_effect(b2_key: str, local_path: Path) -> None:
        if b2_key == "jobs/job-1/input/bundle.tar.gz":
            _write_bundle_tar(local_path)
        elif b2_key == "jobs/job-1/checkpoints/latest":
            local_path.write_bytes(b"prior-checkpoint")
        else:
            raise AssertionError(f"Unexpected download key: {b2_key}")

    storage.download_file.side_effect = download_side_effect
    monkeypatch.setattr("relaymd.worker.main._build_storage_client", lambda *_: storage)
    monkeypatch.setattr("relaymd.worker.main.detect_gpu_info", lambda: ("NVIDIA A100", 2, 80))
    monkeypatch.setattr(
        "relaymd.worker.main.WorkerRuntimeSettings",
        lambda: SimpleNamespace(
            worker_platform="salad",
            heartbeat_interval_seconds=1,
            orchestrator_timeout_seconds=1.0,
            orchestrator_register_max_attempts=3,
            checkpoint_poll_interval_seconds=0,
            sigterm_checkpoint_wait_seconds=1,
            sigterm_checkpoint_poll_seconds=1,
            sigterm_process_wait_seconds=1,
        ),
    )

    heartbeat_thread = Mock()
    monkeypatch.setattr(
        "relaymd.worker.main.HeartbeatThread",
        lambda *args, **kwargs: heartbeat_thread,
    )
    monkeypatch.setattr("relaymd.worker.main.signal.getsignal", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.signal.signal", lambda *_: None)
    monkeypatch.setattr("relaymd.worker.main.time.sleep", lambda *_: None)

    process = Mock()
    process.poll.side_effect = [None, 0, 0, 0]
    monkeypatch.setattr(
        "relaymd.worker.job_execution.subprocess.Popen",
        lambda *args, **kwargs: process,
    )

    api_calls: list[str] = []
    request_responses = iter(
        [
            ApiJobAssigned.from_dict(
                {
                    "status": "assigned",
                    "job_id": "6bd48968-0ecf-4205-9f59-091ec74e7f79",
                    "input_bundle_path": "jobs/job-1/input/bundle.tar.gz",
                    "latest_checkpoint_path": "jobs/job-1/checkpoints/latest",
                }
            ),
            ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ]
    )

    class _FakeGateway:
        def register_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/register")
            return "0a05f971-0f5b-46cb-bd86-d13133f998aa"

        def request_job(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/request")
            return next(request_responses)

        def report_checkpoint(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoint")

        def complete_job(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/complete")

        def fail_job(self, **kwargs):
            _ = kwargs
            raise AssertionError("fail endpoint should not be called")

        def deregister_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister")

    class _FakeGatewayContext:
        def __enter__(self):
            return _FakeGateway()

        def __exit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    monkeypatch.setattr(
        "relaymd.worker.main.ApiOrchestratorGateway",
        lambda **kwargs: _FakeGatewayContext(),
    )

    run_worker(config)

    storage.download_file.assert_any_call("jobs/job-1/input/bundle.tar.gz", ANY)
    storage.download_file.assert_any_call("jobs/job-1/checkpoints/latest", ANY)
    storage.upload_file.assert_called_with(
        ANY,
        "jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoints/latest",
    )

    assert api_calls == [
        "/workers/register",
        "/jobs/request",
        "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoint",
        "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/complete",
        "/jobs/request",
        "/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister",
    ]

    heartbeat_thread.start.assert_called_once_with()
    heartbeat_thread.join.assert_called_once_with(timeout=5)


def test_detect_gpu_fallback_when_pynvml_fails(monkeypatch) -> None:
    def raising_module():
        raise RuntimeError("nvml unavailable")

    monkeypatch.setattr("relaymd.worker.main._get_pynvml_module", raising_module)

    from relaymd.worker.main import detect_gpu_info

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    assert (gpu_model, gpu_count, vram_gb) == ("unknown", 0, 0)


def test_sigterm_request_triggers_graceful_deregister(monkeypatch) -> None:
    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:8000",
    )

    monkeypatch.setattr("relaymd.worker.main._build_storage_client", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.detect_gpu_info", lambda: ("NVIDIA A100", 2, 80))
    monkeypatch.setattr(
        "relaymd.worker.main.WorkerRuntimeSettings",
        lambda: SimpleNamespace(
            worker_platform="salad",
            heartbeat_interval_seconds=1,
            orchestrator_timeout_seconds=1.0,
            orchestrator_register_max_attempts=3,
            checkpoint_poll_interval_seconds=1,
            sigterm_checkpoint_wait_seconds=1,
            sigterm_checkpoint_poll_seconds=1,
            sigterm_process_wait_seconds=1,
        ),
    )

    heartbeat_thread = Mock()
    monkeypatch.setattr(
        "relaymd.worker.main.HeartbeatThread",
        lambda *args, **kwargs: heartbeat_thread,
    )

    captured_handler: dict[str, Callable[[int, object | None], None]] = {}
    monkeypatch.setattr("relaymd.worker.main.signal.getsignal", lambda *_: Mock())

    def register_handler(signum: int, handler: Callable[[int, object | None], None]) -> None:
        if signum == signal.SIGTERM:
            captured_handler["handler"] = handler

    monkeypatch.setattr("relaymd.worker.main.signal.signal", register_handler)

    api_calls: list[str] = []

    class _FakeGateway:
        def register_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/register")
            return "0a05f971-0f5b-46cb-bd86-d13133f998aa"

        def request_job(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/request")
            handler = captured_handler["handler"]
            handler(signal.SIGTERM, None)
            return ApiNoJobAvailable.from_dict({"status": "no_job_available"})

        def report_checkpoint(self, **kwargs):
            _ = kwargs

        def complete_job(self, **kwargs):
            _ = kwargs

        def fail_job(self, **kwargs):
            _ = kwargs

        def deregister_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister")

    class _FakeGatewayContext:
        def __enter__(self):
            return _FakeGateway()

        def __exit__(self, exc_type, exc, tb):
            _ = (exc_type, exc, tb)
            return False

    monkeypatch.setattr(
        "relaymd.worker.main.ApiOrchestratorGateway",
        lambda **kwargs: _FakeGatewayContext(),
    )

    run_worker(config)

    assert api_calls == [
        "/workers/register",
        "/jobs/request",
        "/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister",
    ]
    heartbeat_thread.start.assert_called_once_with()
    heartbeat_thread.join.assert_called_once_with(timeout=5)


def test_run_assigned_job_uses_shutdown_wait_instead_of_sleep(monkeypatch) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-1/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            self._poll_calls = 0
            self._running = True

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def poll_exit_code(self) -> int | None:
            self._poll_calls += 1
            if self._poll_calls == 1:
                return None
            self._running = False
            return 0

        def latest_checkpoint(self) -> None:
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            raise AssertionError("request_terminate should not be called")

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            return 0

        def kill(self) -> None:
            raise AssertionError("kill should not be called")

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_glob_pattern="*.chk",
        ),
    )
    monkeypatch.setattr(
        "relaymd.worker.main.time.sleep",
        lambda *_: (_ for _ in ()).throw(AssertionError("time.sleep should not be called")),
    )

    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = False
    shutdown_event.wait.return_value = False
    logger = Mock()
    logger.bind.return_value = Mock()

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=7,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
    )

    _run_assigned_job(context=context, assignment=assignment)

    assert shutdown_event.wait.call_count == 1
    assert shutdown_event.wait.call_args.kwargs == {"timeout": 2.0}
    gateway.complete_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.fail_job.assert_not_called()


def test_run_assigned_job_polls_exit_frequently_without_checkpoint_churn(monkeypatch) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-fast-exit/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            self._poll_calls = 0
            self._running = True
            self.iter_calls = 0

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            self.iter_calls += 1
            return iter(())

        def poll_exit_code(self) -> int | None:
            self._poll_calls += 1
            if self._poll_calls < 4:
                return None
            self._running = False
            return 0

        def latest_checkpoint(self) -> None:
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            raise AssertionError("request_terminate should not be called")

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            return 0

        def kill(self) -> None:
            raise AssertionError("kill should not be called")

    execution_holder: dict[str, _FakeExecution] = {}

    def _fake_execution_factory(**kwargs) -> _FakeExecution:
        execution = _FakeExecution(**kwargs)
        execution_holder["execution"] = execution
        return execution

    current_time = 0.0

    def _monotonic() -> float:
        return current_time

    def _wait(*, timeout: float) -> bool:
        nonlocal current_time
        current_time += timeout
        return False

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _fake_execution_factory)
    monkeypatch.setattr("relaymd.worker.main.time.monotonic", _monotonic)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_glob_pattern="*.chk",
        ),
    )
    monkeypatch.setattr(
        "relaymd.worker.main.time.sleep",
        lambda *_: (_ for _ in ()).throw(AssertionError("time.sleep should not be called")),
    )

    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = False
    shutdown_event.wait.side_effect = _wait
    logger = Mock()
    logger.bind.return_value = Mock()

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=300,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
    )

    _run_assigned_job(context=context, assignment=assignment)

    execution = execution_holder["execution"]
    assert execution.iter_calls == 1
    assert shutdown_event.wait.call_count == 3
    assert all(call.kwargs == {"timeout": 2.0} for call in shutdown_event.wait.call_args_list)
    gateway.complete_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.fail_job.assert_not_called()


def test_run_assigned_job_terminates_execution_on_exception(monkeypatch, tmp_path: Path) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-2/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            self._running = True
            self.request_terminate_calls = 0
            self.wait_calls = 0
            self.kill_calls = 0

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            yield tmp_path / "checkpoint.chk"

        def poll_exit_code(self) -> int | None:
            return None

        def latest_checkpoint(self):
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            self.request_terminate_calls += 1

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            self.wait_calls += 1
            self._running = False
            return 0

        def kill(self) -> None:
            self.kill_calls += 1

    execution_holder: dict[str, _FakeExecution] = {}

    def _fake_execution_factory(**kwargs) -> _FakeExecution:
        execution = _FakeExecution(**kwargs)
        execution_holder["execution"] = execution
        return execution

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _fake_execution_factory)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_glob_pattern="*.chk",
        ),
    )
    monkeypatch.setattr(
        "relaymd.worker.main._upload_checkpoint",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("upload failed")),
    )

    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = False
    shutdown_event.wait.return_value = False
    logger = Mock()
    logger.bind.return_value = Mock()

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=7,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
    )

    with pytest.raises(RuntimeError, match="upload failed"):
        _run_assigned_job(context=context, assignment=assignment)

    execution = execution_holder["execution"]
    assert execution.request_terminate_calls == 1
    assert execution.wait_calls == 1
    assert execution.kill_calls == 0
