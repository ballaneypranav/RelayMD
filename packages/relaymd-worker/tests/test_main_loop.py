from __future__ import annotations

import io
import os
import signal
import tarfile
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, Mock
from uuid import uuid4

import pytest
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.config import WorkerRuntimeSettings
from relaymd.worker.context import WorkerContext
from relaymd.worker.main import (
    BundleExecutionConfig,
    _build_storage_client,
    _load_bundle_execution_config,
    _run_assigned_job,
    _upload_checkpoint,
    _wait_for_final_checkpoint,
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
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )
    runtime_settings = WorkerRuntimeSettings(
        axiom_token="test",
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )

    _build_storage_client(config, runtime_settings)

    assert captured["cf_bearer_token"] == "download-token"


def test_load_bundle_execution_config_reads_checkpoint_poll_interval_json(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        '{"command": ["bash", "run.sh"], "checkpoint_glob_pattern": "*.chk", '
        '"checkpoint_poll_interval_seconds": 60}\n',
        encoding="utf-8",
    )
    config = _load_bundle_execution_config(tmp_path)
    assert config.checkpoint_poll_interval_seconds == 60


def test_load_bundle_execution_config_reads_checkpoint_poll_interval_toml(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.toml").write_text(
        'command = ["bash", "run.sh"]\ncheckpoint_glob_pattern = "*.chk"\n'
        "checkpoint_poll_interval_seconds = 90\n",
        encoding="utf-8",
    )
    config = _load_bundle_execution_config(tmp_path)
    assert config.checkpoint_poll_interval_seconds == 90


def test_load_bundle_execution_config_rejects_non_positive_checkpoint_poll_interval(
    tmp_path: Path,
) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        '{"command": ["bash", "run.sh"], "checkpoint_glob_pattern": "*.chk", '
        '"checkpoint_poll_interval_seconds": 0}\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid checkpoint_poll_interval_seconds"):
        _load_bundle_execution_config(tmp_path)


def test_load_bundle_execution_config_rejects_boolean_checkpoint_poll_interval(
    tmp_path: Path,
) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        '{"command": ["bash", "run.sh"], "checkpoint_glob_pattern": "*.chk", '
        '"checkpoint_poll_interval_seconds": true}\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid checkpoint_poll_interval_seconds"):
        _load_bundle_execution_config(tmp_path)


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
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )

    runtime_settings = WorkerRuntimeSettings(
        axiom_token="test",
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )
    _build_storage_client(config, runtime_settings)
    assert captured["cf_bearer_token"] == "runtime-token"

    runtime_settings = WorkerRuntimeSettings(
        axiom_token="test",
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
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
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
            idle_strategy="immediate_exit",
            idle_poll_interval_seconds=1,
            idle_poll_max_seconds=1,
            axiom_token="test",
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
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
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
            idle_strategy="immediate_exit",
            idle_poll_interval_seconds=1,
            idle_poll_max_seconds=1,
            axiom_token="test",
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


def test_upload_checkpoint_emits_success_events(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.chk"
    checkpoint.write_text("checkpoint-data", encoding="utf-8")
    storage = Mock()
    gateway = Mock()
    logger = Mock()
    context = cast(WorkerContext, SimpleNamespace(storage=storage, gateway=gateway))
    job_id = uuid4()

    uploaded_mtime = _upload_checkpoint(
        context,
        logger=logger,
        checkpoint=checkpoint,
        checkpoint_b2_key="jobs/x/checkpoints/latest",
        job_id=job_id,
    )

    storage.upload_file.assert_called_once_with(checkpoint, "jobs/x/checkpoints/latest")
    gateway.report_checkpoint.assert_called_once_with(
        job_id=job_id,
        checkpoint_path="jobs/x/checkpoints/latest",
    )
    assert uploaded_mtime == checkpoint.stat().st_mtime
    assert [call.args[0] for call in logger.info.call_args_list] == [
        "checkpoint_upload_started",
        "checkpoint_upload_succeeded",
        "checkpoint_report_succeeded",
    ]


def test_upload_checkpoint_emits_failure_event(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.chk"
    checkpoint.write_text("checkpoint-data", encoding="utf-8")
    storage = Mock()
    storage.upload_file.side_effect = RuntimeError("boom")
    gateway = Mock()
    logger = Mock()
    context = cast(WorkerContext, SimpleNamespace(storage=storage, gateway=gateway))

    with pytest.raises(RuntimeError, match="boom"):
        _upload_checkpoint(
            context,
            logger=logger,
            checkpoint=checkpoint,
            checkpoint_b2_key="jobs/x/checkpoints/latest",
            job_id=uuid4(),
        )

    logger.exception.assert_called_once()
    assert logger.exception.call_args.args[0] == "checkpoint_upload_failed"
    gateway.report_checkpoint.assert_not_called()


def test_wait_for_final_checkpoint_respects_min_mtime(tmp_path: Path) -> None:
    checkpoint = tmp_path / "relaymd-checkpoint.tar.gz"
    checkpoint.write_text("old", encoding="utf-8")
    os.utime(checkpoint, (100.0, 100.0))

    no_newer = _wait_for_final_checkpoint(
        tmp_path,
        "relaymd-checkpoint.tar.gz",
        timeout_seconds=0,
        poll_interval_seconds=1,
        min_checkpoint_mtime=100.0,
    )
    assert no_newer is None

    newer_allowed = _wait_for_final_checkpoint(
        tmp_path,
        "relaymd-checkpoint.tar.gz",
        timeout_seconds=0,
        poll_interval_seconds=1,
        min_checkpoint_mtime=99.0,
    )
    assert newer_allowed == checkpoint


def test_run_assigned_job_shutdown_uploads_newer_checkpoint(monkeypatch) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-shutdown/input/bundle.tar.gz",
            "latest_checkpoint_path": "jobs/job-shutdown/checkpoints/latest",
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            self.workdir = kwargs["workdir"]
            self.checkpoint = self.workdir / "relaymd-checkpoint.tar.gz"
            self.checkpoint.write_text("old", encoding="utf-8")
            os.utime(self.checkpoint, (100.0, 100.0))
            self._running = False

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def poll_exit_code(self) -> int | None:
            return None

        def latest_checkpoint(self):
            return self.checkpoint

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            self.checkpoint.write_text("new", encoding="utf-8")
            os.utime(self.checkpoint, (200.0, 200.0))

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            return 0

        def kill(self) -> None:
            raise AssertionError("kill should not be called")

    uploaded_mtimes: list[float] = []

    def _fake_upload_checkpoint(*args, **kwargs) -> float:
        checkpoint_mtime = kwargs["checkpoint"].stat().st_mtime
        uploaded_mtimes.append(checkpoint_mtime)
        return checkpoint_mtime

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)
    monkeypatch.setattr("relaymd.worker.main._upload_checkpoint", _fake_upload_checkpoint)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_glob_pattern="relaymd-checkpoint.tar.gz",
        ),
    )

    storage = Mock()

    def _download_file(_remote: str, local: Path) -> None:
        local.write_bytes(b"bundle-data")

    storage.download_file.side_effect = _download_file
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = True
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

    assert uploaded_mtimes == [200.0]
    gateway.complete_job.assert_not_called()
    gateway.fail_job.assert_not_called()


def test_run_assigned_job_shutdown_skips_stale_checkpoint_for_resumed_job(
    monkeypatch,
) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-resume/input/bundle.tar.gz",
            "latest_checkpoint_path": "jobs/job-resume/checkpoints/latest",
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            self.workdir = kwargs["workdir"]
            self.checkpoint = self.workdir / "relaymd-checkpoint.tar.gz"
            self.checkpoint.write_text("old", encoding="utf-8")
            os.utime(self.checkpoint, (100.0, 100.0))
            self._running = False

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def poll_exit_code(self) -> int | None:
            return None

        def latest_checkpoint(self):
            return self.checkpoint

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            return None

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
            checkpoint_glob_pattern="relaymd-checkpoint.tar.gz",
        ),
    )

    upload_checkpoint = Mock()
    monkeypatch.setattr("relaymd.worker.main._upload_checkpoint", upload_checkpoint)

    storage = Mock()

    def _download_file(_remote: str, local: Path) -> None:
        local.write_bytes(b"bundle-data")

    storage.download_file.side_effect = _download_file
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = True
    logger = Mock()
    logger.bind.return_value = Mock()

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=7,
        sigterm_checkpoint_wait_seconds=0,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
    )

    _run_assigned_job(context=context, assignment=assignment)

    upload_checkpoint.assert_not_called()
    gateway.complete_job.assert_not_called()
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


def test_run_worker_poll_then_exit_timeout(monkeypatch) -> None:
    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )

    monkeypatch.setattr("relaymd.worker.main._build_storage_client", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.detect_gpu_info", lambda: ("NVIDIA A100", 2, 80))

    runtime_settings = SimpleNamespace(
        worker_platform="salad",
        heartbeat_interval_seconds=1,
        orchestrator_timeout_seconds=1.0,
        orchestrator_register_max_attempts=3,
        checkpoint_poll_interval_seconds=1,
        sigterm_checkpoint_wait_seconds=1,
        sigterm_checkpoint_poll_seconds=1,
        sigterm_process_wait_seconds=1,
        idle_strategy="poll_then_exit",
        idle_poll_interval_seconds=10,
        idle_poll_max_seconds=25,
        axiom_token="test",
    )
    monkeypatch.setattr("relaymd.worker.main.WorkerRuntimeSettings", lambda: runtime_settings)

    heartbeat_thread = Mock()
    monkeypatch.setattr(
        "relaymd.worker.main.HeartbeatThread", lambda *args, **kwargs: heartbeat_thread
    )

    monkeypatch.setattr("relaymd.worker.main.signal.getsignal", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.signal.signal", lambda *_: None)

    # Mock time.monotonic to simulate passing time
    current_time = 0.0

    def _monotonic():
        return current_time

    monkeypatch.setattr("relaymd.worker.main.time.monotonic", _monotonic)

    api_calls: list[str] = []

    class _FakeGateway:
        def register_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/register")
            return "0a05f971-0f5b-46cb-bd86-d13133f998aa"

        def request_job(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/request")
            return ApiNoJobAvailable.from_dict({"status": "no_job_available"})

        def report_checkpoint(self, **kwargs):
            pass

        def complete_job(self, **kwargs):
            pass

        def fail_job(self, **kwargs):
            pass

        def deregister_worker(self, **kwargs):
            _ = kwargs
            api_calls.append("/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister")

    class _FakeGatewayContext:
        def __enter__(self):
            return _FakeGateway()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "relaymd.worker.main.ApiOrchestratorGateway", lambda **kwargs: _FakeGatewayContext()
    )

    # We need to simulate shutdown_event.wait taking time and advancing monotonic time
    original_event = threading.Event

    class _FakeEvent(original_event):
        def wait(self, timeout=None):
            nonlocal current_time
            if timeout is not None:
                current_time += timeout
            return super().wait(timeout=0)  # Don't actually sleep

    monkeypatch.setattr("relaymd.worker.main.threading.Event", _FakeEvent)

    run_worker(config)

    # We expect 4 requests:
    # 1. t=0 (first request, starts poll)
    # 2. t=10 (waited 10s)
    # 3. t=20 (waited 10s)
    # 4. t=30 (waited 10s, exceeds max 25s, so breaks)
    assert api_calls == [
        "/workers/register",
        "/jobs/request",
        "/jobs/request",
        "/jobs/request",
        "/jobs/request",
        "/workers/0a05f971-0f5b-46cb-bd86-d13133f998aa/deregister",
    ]


def test_run_worker_poll_then_exit_finds_job(monkeypatch) -> None:
    config = WorkerConfig(
        b2_application_key_id="id",
        b2_application_key="secret",
        b2_endpoint="https://s3.us-east-005.backblazeb2.com",
        bucket_name="relaymd-bucket",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )

    monkeypatch.setattr("relaymd.worker.main._build_storage_client", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.detect_gpu_info", lambda: ("NVIDIA A100", 2, 80))

    runtime_settings = SimpleNamespace(
        worker_platform="salad",
        heartbeat_interval_seconds=1,
        orchestrator_timeout_seconds=1.0,
        orchestrator_register_max_attempts=3,
        checkpoint_poll_interval_seconds=1,
        sigterm_checkpoint_wait_seconds=1,
        sigterm_checkpoint_poll_seconds=1,
        sigterm_process_wait_seconds=1,
        idle_strategy="poll_then_exit",
        idle_poll_interval_seconds=10,
        idle_poll_max_seconds=600,
        axiom_token="test",
    )
    monkeypatch.setattr("relaymd.worker.main.WorkerRuntimeSettings", lambda: runtime_settings)

    heartbeat_thread = Mock()
    monkeypatch.setattr(
        "relaymd.worker.main.HeartbeatThread", lambda *args, **kwargs: heartbeat_thread
    )

    monkeypatch.setattr("relaymd.worker.main.signal.getsignal", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.signal.signal", lambda *_: None)

    current_time = 0.0
    monkeypatch.setattr("relaymd.worker.main.time.monotonic", lambda: current_time)

    # Mock _run_assigned_job to avoid setting up job config
    job_run_calls = []

    def _mock_run_job(*args, **kwargs):
        job_run_calls.append(kwargs.get("assignment", args[1] if len(args) > 1 else None))

    monkeypatch.setattr("relaymd.worker.main._run_assigned_job", _mock_run_job)

    api_calls: list[str] = []
    job_1_id = "6bd48968-0ecf-4205-9f59-091ec74e7f79"
    job_2_id = "7bd48968-0ecf-4205-9f59-091ec74e7f80"

    # 1: assign job 1
    # 2: no job (idle starts)
    # 3: no job (idle continues)
    # 4: assign job 2
    # 5: no job (idle starts again)
    # 6: no job (idle continues)
    responses = [
        ApiJobAssigned.from_dict(
            {
                "status": "assigned",
                "job_id": job_1_id,
                "input_bundle_path": "a",
                "latest_checkpoint_path": None,
            }
        ),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ApiJobAssigned.from_dict(
            {
                "status": "assigned",
                "job_id": job_2_id,
                "input_bundle_path": "a",
                "latest_checkpoint_path": None,
            }
        ),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
        ApiNoJobAvailable.from_dict({"status": "no_job_available"}),
    ]
    response_iter = iter(responses)

    class _FakeGateway:
        def register_worker(self, **kwargs):
            return "0a05f971-0f5b-46cb-bd86-d13133f998aa"

        def request_job(self, **kwargs):
            api_calls.append("/jobs/request")
            try:
                return next(response_iter)
            except StopIteration:
                return ApiNoJobAvailable.from_dict({"status": "no_job_available"})

        def report_checkpoint(self, **kwargs):
            pass

        def complete_job(self, **kwargs):
            pass

        def fail_job(self, **kwargs):
            pass

        def deregister_worker(self, **kwargs):
            pass

    class _FakeGatewayContext:
        def __enter__(self):
            return _FakeGateway()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "relaymd.worker.main.ApiOrchestratorGateway", lambda **kwargs: _FakeGatewayContext()
    )

    original_event = threading.Event

    class _FakeEvent(original_event):
        def wait(self, timeout=None):
            nonlocal current_time
            if timeout is not None:
                current_time += timeout

            # Artificial test termination after enough time to prove loop logic restores
            if current_time > 100:
                self.set()
                return True

            return super().wait(timeout=0)

    monkeypatch.setattr("relaymd.worker.main.threading.Event", _FakeEvent)

    run_worker(config)

    assert len(job_run_calls) == 2
    assert str(job_run_calls[0].job_id) == job_1_id
    assert str(job_run_calls[1].job_id) == job_2_id
