from __future__ import annotations

import io
import json
import os
import signal
import tarfile
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, Mock, call
from uuid import uuid4

import pytest
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.config import WorkerRuntimeSettings
from relaymd.worker.context import WorkerContext
from relaymd.worker.heartbeat import HeartbeatHealthSnapshot, HeartbeatThread
from relaymd.worker.main import (
    PROGRESS_INVALID_FORMAT,
    PROGRESS_MISSING,
    BundleExecutionConfig,
    _build_storage_client,
    _extract_input_bundle,
    _load_bundle_execution_config,
    _read_progress,
    _required_openmm_platform,
    _run_assigned_job,
    detect_openmm_platforms,
    run_worker,
)
from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable


def _write_bundle_tar(local_path: Path) -> None:
    bundle_config = (
        b'{"command": ["md-engine", "--run"], '
        b'"checkpoint_watch_paths": ["*.chk"], '
        b'"progress_file_path": "progress.txt"}'
    )
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
        storage_provider="cloudflare_backblaze",
        axiom_token="test",
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )

    _build_storage_client(config, runtime_settings)

    assert captured["cf_bearer_token"] == "download-token"


def test_load_bundle_execution_config_reads_checkpoint_poll_interval_json(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["bash", "run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt", '
            '"checkpoint_poll_interval_seconds": 60}\n'
        ),
        encoding="utf-8",
    )
    config = _load_bundle_execution_config(tmp_path)
    assert config.checkpoint_poll_interval_seconds == 60


def test_load_bundle_execution_config_reads_supervision_fields_json(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["bash", "run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt", '
            '"progress_glob_pattern": ["progress", "r*/job.out"], '
            '"startup_progress_timeout_seconds": 60, '
            '"progress_timeout_seconds": 120, '
            '"max_runtime_seconds": 3600, '
            '"fatal_log_path": "job.log", '
            '"fatal_log_patterns": ["Traceback", "CUDA_ERROR"]}\n'
        ),
        encoding="utf-8",
    )

    config = _load_bundle_execution_config(tmp_path)

    assert config.progress_glob_patterns == ["progress", "r*/job.out"]
    assert config.startup_progress_timeout_seconds == 60
    assert config.progress_timeout_seconds == 120
    assert config.max_runtime_seconds == 3600
    assert config.fatal_log_path == "job.log"
    assert config.fatal_log_patterns == ["Traceback", "CUDA_ERROR"]


def test_load_bundle_execution_config_reads_checkpoint_poll_interval_toml(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.toml").write_text(
        (
            'command = ["bash", "run.sh"]\n'
            'checkpoint_watch_paths = ["*.chk"]\n'
            'progress_file_path = "progress.txt"\n'
            "checkpoint_poll_interval_seconds = 90\n"
        ),
        encoding="utf-8",
    )
    config = _load_bundle_execution_config(tmp_path)
    assert config.checkpoint_poll_interval_seconds == 90


def test_read_progress_reads_relative_path_and_rejects_absolute(tmp_path: Path) -> None:
    (tmp_path / "progress.txt").write_text("0.75\n", encoding="utf-8")
    progress, codes = _read_progress(bundle_root=tmp_path, progress_file_path="progress.txt")
    assert progress == 0.75
    assert codes == []

    absolute_path = str((tmp_path / "progress.txt").resolve())
    invalid_progress, invalid_codes = _read_progress(
        bundle_root=tmp_path, progress_file_path=absolute_path
    )
    assert invalid_progress == 0.0
    assert invalid_codes == [PROGRESS_INVALID_FORMAT]

    missing_progress, missing_codes = _read_progress(
        bundle_root=tmp_path, progress_file_path="missing.txt"
    )
    assert missing_progress == 0.0
    assert missing_codes == [PROGRESS_MISSING]


def test_load_bundle_execution_config_reads_supervision_fields_toml(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.toml").write_text(
        "\n".join(
            [
                'command = ["bash", "run.sh"]',
                'checkpoint_watch_paths = ["*.chk"]',
                'progress_file_path = "progress.txt"',
                'progress_glob_pattern = "progress"',
                "startup_progress_timeout_seconds = 60",
                "progress_timeout_seconds = 120",
                "max_runtime_seconds = 3600",
                'fatal_log_path = "job.log"',
                'fatal_log_patterns = ["Traceback", "CUDA_ERROR"]',
            ]
        ),
        encoding="utf-8",
    )

    config = _load_bundle_execution_config(tmp_path)

    assert config.progress_glob_patterns == ["progress"]
    assert config.startup_progress_timeout_seconds == 60
    assert config.progress_timeout_seconds == 120
    assert config.max_runtime_seconds == 3600
    assert config.fatal_log_path == "job.log"
    assert config.fatal_log_patterns == ["Traceback", "CUDA_ERROR"]


def test_load_bundle_execution_config_rejects_non_positive_checkpoint_poll_interval(
    tmp_path: Path,
) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["bash", "run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt", '
            '"checkpoint_poll_interval_seconds": 0}\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid checkpoint_poll_interval_seconds"):
        _load_bundle_execution_config(tmp_path)


def test_load_bundle_execution_config_rejects_boolean_checkpoint_poll_interval(
    tmp_path: Path,
) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["bash", "run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt", '
            '"checkpoint_poll_interval_seconds": true}\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid checkpoint_poll_interval_seconds"):
        _load_bundle_execution_config(tmp_path)


def test_load_bundle_execution_config_rejects_invalid_supervision_field(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["bash", "run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt", '
            '"progress_timeout_seconds": false}\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Invalid progress_timeout_seconds"):
        _load_bundle_execution_config(tmp_path)


def test_extract_input_bundle_extracts_tar_on_python_311(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    output_dir = tmp_path / "bundle-out"
    payload = b'{"command":["echo","hello"]}\n'
    with tarfile.open(bundle, "w:gz") as archive:
        info = tarfile.TarInfo("relaymd-worker.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    extracted = _extract_input_bundle(bundle, output_dir)
    assert extracted == output_dir
    assert (output_dir / "relaymd-worker.json").read_bytes() == payload


def test_extract_input_bundle_rejects_path_traversal_entries(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.tar.gz"
    output_dir = tmp_path / "bundle-out"
    payload = b"bad"
    with tarfile.open(bundle, "w:gz") as archive:
        info = tarfile.TarInfo("../evil.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(
        (RuntimeError, tarfile.TarError), match="path traversal|outside the destination"
    ):
        _extract_input_bundle(bundle, output_dir)


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
        storage_provider="cloudflare_backblaze",
        axiom_token="test",
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )
    _build_storage_client(config, runtime_settings)
    assert captured["cf_bearer_token"] == "runtime-token"

    runtime_settings = WorkerRuntimeSettings(
        storage_provider="cloudflare_backblaze",
        axiom_token="test",
        cf_worker_url="https://cf.example",
        cf_bearer_token="",
    )
    _build_storage_client(config, runtime_settings)
    assert captured["cf_bearer_token"] == "api-token"


def test_build_storage_client_uses_purdue_credentials(monkeypatch) -> None:
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
        purdue_s3_access_key="purdue-access",
        purdue_s3_secret_key="purdue-secret",
        purdue_s3_endpoint="https://s3.rcac.purdue.edu",
        purdue_s3_bucket_name="purdue-bucket",
        tailscale_auth_key="tskey",
        relaymd_api_token="api-token",
        relaymd_orchestrator_url="http://orchestrator.tail.ts.net:36158",
    )
    runtime_settings = WorkerRuntimeSettings(
        axiom_token="test",
        storage_provider="purdue",
        cf_worker_url="https://cf.example",
        cf_bearer_token="runtime-token",
    )

    _build_storage_client(config, runtime_settings)

    assert captured["storage_provider"] == "purdue"
    assert captured["b2_endpoint_url"] == "https://s3.rcac.purdue.edu"
    assert captured["b2_bucket_name"] == "purdue-bucket"
    assert captured["b2_access_key_id"] == "purdue-access"
    assert captured["b2_secret_access_key"] == "purdue-secret"
    assert captured["s3_region_name"] == "us-east-1"


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

        def start_job(self, **kwargs):
            _ = kwargs
            api_calls.append("/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/start")

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
        "jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoints/manifest.json",
    )

    assert api_calls[0:3] == [
        "/workers/register",
        "/jobs/request",
        "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/start",
    ]
    assert "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoint" in api_calls
    assert "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/complete" in api_calls
    assert api_calls[-2:] == [
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


def test_detect_openmm_platforms_returns_empty_list_when_import_fails(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def _failing_import(name, *args, **kwargs):
        if name == "openmm":
            raise ModuleNotFoundError("openmm not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _failing_import)

    assert detect_openmm_platforms() == []


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

        def start_job(self, **kwargs):
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
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
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
        openmm_platforms=[],
    )

    _run_assigned_job(context=context, assignment=assignment)

    assert shutdown_event.wait.call_count == 1
    assert shutdown_event.wait.call_args.kwargs == {"timeout": 2.0}
    assert gateway.method_calls[0] == call.start_job(job_id=assignment.job_id)
    assert call.complete_job(job_id=assignment.job_id) in gateway.method_calls
    report_calls = [
        method_call for method_call in gateway.method_calls if method_call[0] == "report_checkpoint"
    ]
    assert report_calls
    assert all(
        method_call.kwargs["job_id"] == assignment.job_id
        and method_call.kwargs["checkpoint_path"]
        == f"jobs/{assignment.job_id}/checkpoints/manifest.json"
        for method_call in report_calls
    )
    gateway.start_job.assert_called_once_with(job_id=assignment.job_id)
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
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
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
        openmm_platforms=[],
    )

    _run_assigned_job(context=context, assignment=assignment)

    execution = execution_holder["execution"]
    assert execution.iter_calls == 0
    assert shutdown_event.wait.call_count == 3
    assert all(call.kwargs == {"timeout": 2.0} for call in shutdown_event.wait.call_args_list)
    gateway.start_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.complete_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.fail_job.assert_not_called()


def test_run_assigned_job_fatal_log_failure_uploads_log_as_checkpoint(monkeypatch) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-supervision/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            self.workdir = kwargs["workdir"]
            self._running = True
            self.request_terminate_calls = 0
            self.wait_calls = 0
            self.kill_calls = 0

        def start(self) -> None:
            (self.workdir / "payload.log").write_text(
                "Traceback: child failed\n",
                encoding="utf-8",
            )
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def supervision_failure(self, *, now: float):
            _ = now
            return SimpleNamespace(reason="fatal_log_match", detail="fatal log pattern matched")

        def poll_exit_code(self) -> int | None:
            return None

        def latest_checkpoint(self):
            return None

        def result(self):
            raise AssertionError("result should not be used after supervision failure")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            self.request_terminate_calls += 1

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            self.wait_calls += 1
            if self.wait_calls == 1:
                return None
            self._running = False
            return -signal.SIGKILL

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
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
            fatal_log_path="payload.log",
            fatal_log_patterns=["Traceback"],
        ),
    )

    uploaded: dict[str, object] = {}
    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    storage.upload_file.side_effect = lambda local, remote: uploaded.update(
        path=local,
        key=remote,
        content=local.read_text(encoding="utf-8"),
    )
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
        openmm_platforms=[],
    )

    _run_assigned_job(context=context, assignment=assignment)

    execution = execution_holder["execution"]
    assert execution.request_terminate_calls == 1
    assert execution.kill_calls == 1
    assert storage.upload_file.call_count == 2
    assert cast(Path, uploaded["path"]).name == "relaymd-checkpoint-manifest.json"
    assert uploaded["key"] == f"jobs/{assignment.job_id}/checkpoints/manifest.json"
    report_calls = [
        method_call for method_call in gateway.method_calls if method_call[0] == "report_checkpoint"
    ]
    assert len(report_calls) == 2
    assert all(
        method_call.kwargs["job_id"] == assignment.job_id
        and method_call.kwargs["checkpoint_path"]
        == f"jobs/{assignment.job_id}/checkpoints/manifest.json"
        for method_call in report_calls
    )
    gateway.start_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.fail_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.complete_job.assert_not_called()


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

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_watch_paths=["relaymd-checkpoint.tar.gz"],
            progress_file_path="progress.txt",
        ),
    )

    storage = Mock()
    uploaded_manifest_text: str | None = None

    def _download_file(_remote: str, local: Path) -> None:
        local.write_bytes(b"bundle-data")

    def _upload_file(local: Path, remote: str) -> None:
        nonlocal uploaded_manifest_text
        if remote == f"jobs/{assignment.job_id}/checkpoints/manifest.json":
            uploaded_manifest_text = local.read_text(encoding="utf-8")

    storage.download_file.side_effect = _download_file
    storage.upload_file.side_effect = _upload_file
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
        openmm_platforms=[],
    )

    _run_assigned_job(context=context, assignment=assignment)

    manifest_upload_calls = [
        call_args
        for call_args in storage.upload_file.call_args_list
        if call_args.args[1] == f"jobs/{assignment.job_id}/checkpoints/manifest.json"
    ]
    assert len(manifest_upload_calls) == 1
    assert uploaded_manifest_text is not None
    manifest = json.loads(uploaded_manifest_text)
    checkpoint_entry = manifest["files"]["relaymd-checkpoint.tar.gz"]
    assert checkpoint_entry["mtime_ns"] == int(200.0 * 1_000_000_000)
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
            checkpoint_watch_paths=["relaymd-checkpoint.tar.gz"],
            progress_file_path="progress.txt",
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
        sigterm_checkpoint_wait_seconds=0,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
        openmm_platforms=[],
    )

    _run_assigned_job(context=context, assignment=assignment)

    storage.upload_file.assert_called()
    storage.upload_file.assert_any_call(
        ANY,
        f"jobs/{assignment.job_id}/checkpoints/manifest.json",
    )
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
            return iter(())

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
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
        ),
    )
    monkeypatch.setattr(
        "relaymd.worker.main._sync_checkpoint_manifest_cycle",
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
        openmm_platforms=[],
    )

    with pytest.raises(RuntimeError, match="upload failed"):
        _run_assigned_job(context=context, assignment=assignment)

    execution = execution_holder["execution"]
    assert execution.request_terminate_calls == 1
    assert execution.wait_calls == 1
    assert execution.kill_calls == 0


def test_run_assigned_job_heartbeat_degraded_healthy_checkpoint_keeps_running(
    monkeypatch,
) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-healthy/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            self._poll_calls = 0
            self._running = True
            self.terminate_calls = 0

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def poll_exit_code(self) -> int | None:
            self._poll_calls += 1
            if self._poll_calls < 4:
                return None
            self._running = False
            return 0

        def latest_checkpoint(self):
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            self.terminate_calls += 1

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            return 0

        def kill(self) -> None:
            raise AssertionError("kill should not be called")

    class _FakeHeartbeatThread:
        def __init__(self) -> None:
            self._snapshot = HeartbeatHealthSnapshot(
                consecutive_failures=2,
                degraded_since=0.0,
                last_success_at=None,
            )

        def health_snapshot(self):
            return self._snapshot

        def set_job_progress(self, **kwargs) -> None:
            _ = kwargs

    current_time = 0.0

    def _monotonic() -> float:
        return current_time

    def _wait(*, timeout: float) -> bool:
        nonlocal current_time
        current_time += timeout
        return False

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)
    monkeypatch.setattr("relaymd.worker.main.time.monotonic", _monotonic)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
            checkpoint_poll_interval_seconds=2,
        ),
    )

    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = False
    shutdown_event.wait.side_effect = _wait
    logger = Mock()
    logger.bind.return_value = logger

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=7,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
        openmm_platforms=[],
        heartbeat_interval_seconds=1,
        heartbeat_failure_grace_multiplier=1,
        heartbeat_failure_grace_floor_seconds=3,
        heartbeat_thread=cast(HeartbeatThread, _FakeHeartbeatThread()),
    )

    _run_assigned_job(context=context, assignment=assignment)

    gateway.complete_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.fail_job.assert_not_called()
    logger.warning.assert_any_call(
        "heartbeat_degraded_mode_entered",
        outage_duration_seconds=0.0,
        grace_limit_seconds=3.0,
        checkpoint_report_age_seconds=None,
        checkpoint_health_threshold_seconds=6.0,
        consecutive_failures=2,
    )
    logger.info.assert_any_call(
        "heartbeat_degraded_mode_grace_extended_by_checkpoint_health",
        outage_duration_seconds=2.0,
        grace_limit_seconds=3.0,
        checkpoint_report_age_seconds=2.0,
        checkpoint_health_threshold_seconds=6.0,
    )
    shutdown_logs = [
        args
        for args, _kwargs in logger.warning.call_args_list
        if args and args[0] == "heartbeat_degraded_mode_shutdown_triggered"
    ]
    assert not shutdown_logs


def test_run_assigned_job_heartbeat_degraded_beyond_grace_triggers_shutdown(monkeypatch) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/job-shutdown/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs
            self._running = True
            self.terminate_calls = 0
            self.wait_calls = 0

        def start(self) -> None:
            return None

        def iter_new_checkpoints(self):
            return iter(())

        def poll_exit_code(self) -> int | None:
            return None

        def latest_checkpoint(self):
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self) -> bool:
            return self._running

        def request_terminate(self) -> None:
            self.terminate_calls += 1
            self._running = False

        def wait(self, timeout_seconds: float) -> int | None:
            _ = timeout_seconds
            self.wait_calls += 1
            return 0

        def kill(self) -> None:
            raise AssertionError("kill should not be called")

    class _FakeHeartbeatThread:
        def health_snapshot(self):
            return HeartbeatHealthSnapshot(
                consecutive_failures=5,
                degraded_since=0.0,
                last_success_at=None,
            )

        def set_job_progress(self, **kwargs) -> None:
            _ = kwargs

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)
    monkeypatch.setattr("relaymd.worker.main.time.monotonic", lambda: 5.0)
    monkeypatch.setattr(
        "relaymd.worker.main._load_bundle_execution_config",
        lambda _bundle_root: BundleExecutionConfig(
            command=["echo", "ok"],
            checkpoint_watch_paths=["*.chk"],
            progress_file_path="progress.txt",
            checkpoint_poll_interval_seconds=2,
        ),
    )

    storage = Mock()
    storage.download_file.side_effect = lambda _remote, local: local.write_bytes(b"bundle-data")
    gateway = Mock()
    shutdown_event = Mock()
    shutdown_event.is_set.return_value = False
    shutdown_event.wait.return_value = False
    logger = Mock()
    logger.bind.return_value = logger

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=shutdown_event,
        checkpoint_poll_interval_seconds=7,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
        openmm_platforms=[],
        heartbeat_interval_seconds=1,
        heartbeat_failure_grace_multiplier=1,
        heartbeat_failure_grace_floor_seconds=3,
        heartbeat_thread=cast(HeartbeatThread, _FakeHeartbeatThread()),
    )

    _run_assigned_job(context=context, assignment=assignment)

    gateway.complete_job.assert_not_called()
    gateway.fail_job.assert_not_called()
    logger.warning.assert_any_call(
        "heartbeat_degraded_mode_shutdown_triggered",
        outage_duration_seconds=5.0,
        grace_limit_seconds=3.0,
        checkpoint_report_age_seconds=None,
        checkpoint_health_threshold_seconds=6.0,
    )


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
            _ = kwargs

        def start_job(self, **kwargs):
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
            _ = kwargs

        def start_job(self, **kwargs):
            _ = kwargs

        def complete_job(self, **kwargs):
            _ = kwargs

        def fail_job(self, **kwargs):
            _ = kwargs

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


# ---------------------------------------------------------------------------
# _required_openmm_platform
# ---------------------------------------------------------------------------


def test_required_openmm_platform_returns_none_when_no_yaml(tmp_path: Path) -> None:
    (tmp_path / "relaymd-worker.json").write_text(
        (
            '{"command": ["run.sh"], '
            '"checkpoint_watch_paths": ["*.chk"], '
            '"progress_file_path": "progress.txt"}'
        ),
        encoding="utf-8",
    )
    assert _required_openmm_platform(tmp_path) is None


def test_required_openmm_platform_returns_none_when_yaml_has_no_platform(tmp_path: Path) -> None:
    (tmp_path / "job.yaml").write_text("JOBNAME: test\nCYCLE_TIME: 10\n", encoding="utf-8")
    assert _required_openmm_platform(tmp_path) is None


def test_required_openmm_platform_returns_cuda_from_yaml(tmp_path: Path) -> None:
    (tmp_path / "APT_FOL.yaml").write_text(
        "JOBNAME: APT_FOL\nOPENMM_PLATFORM: CUDA\nCYCLE_TIME: 10\n", encoding="utf-8"
    )
    assert _required_openmm_platform(tmp_path) == "CUDA"


def test_required_openmm_platform_normalises_value_to_upper(tmp_path: Path) -> None:
    (tmp_path / "job.yaml").write_text("OPENMM_PLATFORM: cuda\n", encoding="utf-8")
    assert _required_openmm_platform(tmp_path) == "CUDA"


# ---------------------------------------------------------------------------
# preflight guard in _run_assigned_job
# ---------------------------------------------------------------------------


def _write_bundle_tar_with_yaml(local_path: Path, openmm_platform: str) -> None:
    bundle_config = (
        b'{"command": ["md-engine", "--run"], '
        b'"checkpoint_watch_paths": ["*.chk"], '
        b'"progress_file_path": "progress.txt"}'
    )
    job_yaml = f"JOBNAME: test\nOPENMM_PLATFORM: {openmm_platform}\n".encode()

    with tarfile.open(local_path, "w:gz") as archive:
        config_info = tarfile.TarInfo("relaymd-worker.json")
        config_info.size = len(bundle_config)
        archive.addfile(config_info, io.BytesIO(bundle_config))

        yaml_info = tarfile.TarInfo("job.yaml")
        yaml_info.size = len(job_yaml)
        archive.addfile(yaml_info, io.BytesIO(job_yaml))


def test_run_assigned_job_fails_fast_when_cuda_required_but_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/test-job/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    bundle_tar = tmp_path / "bundle.tar.gz"
    _write_bundle_tar_with_yaml(bundle_tar, "CUDA")

    storage = Mock()
    storage.download_file.side_effect = lambda src, dst: (
        bundle_tar.read_bytes() and dst.write_bytes(bundle_tar.read_bytes())
    )
    gateway = Mock()
    logger = Mock()
    logger.bind.return_value = logger

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=threading.Event(),
        checkpoint_poll_interval_seconds=60,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
        openmm_platforms=["Reference", "CPU"],
    )

    _run_assigned_job(context=context, assignment=assignment)

    gateway.fail_job.assert_called_once_with(job_id=assignment.job_id)
    gateway.complete_job.assert_not_called()


def test_run_assigned_job_proceeds_when_cuda_required_and_available(
    monkeypatch, tmp_path: Path
) -> None:
    assignment = ApiJobAssigned.from_dict(
        {
            "status": "assigned",
            "job_id": str(uuid4()),
            "input_bundle_path": "jobs/test-job/input/bundle.tar.gz",
            "latest_checkpoint_path": None,
        }
    )

    bundle_tar = tmp_path / "bundle.tar.gz"
    _write_bundle_tar_with_yaml(bundle_tar, "CUDA")

    storage = Mock()
    storage.download_file.side_effect = lambda src, dst: dst.write_bytes(bundle_tar.read_bytes())
    gateway = Mock()
    logger = Mock()
    logger.bind.return_value = logger

    execution_started = []

    class _FakeExecution:
        def __init__(self, **kwargs) -> None:
            _ = kwargs

        def start(self) -> None:
            execution_started.append(True)

        def poll_exit_code(self):
            return 0

        def iter_new_checkpoints(self):
            return iter([])

        def latest_checkpoint(self):
            return None

        def result(self):
            return SimpleNamespace(status="completed")

        def is_running(self):
            return False

        def supervision_failure(self, now):
            return None

    monkeypatch.setattr("relaymd.worker.main.JobExecution", _FakeExecution)

    context = WorkerContext(
        gateway=gateway,
        storage=storage,
        shutdown_event=threading.Event(),
        checkpoint_poll_interval_seconds=60,
        sigterm_checkpoint_wait_seconds=60,
        sigterm_checkpoint_poll_seconds=2,
        sigterm_process_wait_seconds=10,
        logger=logger,
        openmm_platforms=["Reference", "CPU", "CUDA"],
    )

    _run_assigned_job(context=context, assignment=assignment)

    assert execution_started, "JobExecution.start() should have been called"
    gateway.fail_job.assert_not_called()
    gateway.complete_job.assert_called_once_with(job_id=assignment.job_id)
