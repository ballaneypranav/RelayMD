from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import ANY, Mock

from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.main import run_worker


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP error: {self.status_code}")


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

    heartbeat_thread = Mock()
    monkeypatch.setattr(
        "relaymd.worker.main.HeartbeatThread",
        lambda *args, **kwargs: heartbeat_thread,
    )
    heartbeat_stop_event = Mock()
    monkeypatch.setattr("relaymd.worker.main.threading.Event", lambda: heartbeat_stop_event)
    monkeypatch.setattr("relaymd.worker.main.signal.getsignal", lambda *_: Mock())
    monkeypatch.setattr("relaymd.worker.main.signal.signal", lambda *_: None)

    monkeypatch.setattr(
        "relaymd.worker.main.detect_gpu_info",
        lambda: ("NVIDIA A100", 2, 80),
    )

    process = Mock()
    process.poll.side_effect = [None, 0]
    monkeypatch.setattr("relaymd.worker.main.subprocess.Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("relaymd.worker.main.time.sleep", lambda *_: None)

    client = Mock()
    client.post.side_effect = [
        FakeResponse(200, {"worker_id": "0a05f971-0f5b-46cb-bd86-d13133f998aa"}),
        FakeResponse(
            200,
            {
                "status": "assigned",
                "job_id": "6bd48968-0ecf-4205-9f59-091ec74e7f79",
                "input_bundle_path": "jobs/job-1/input/bundle.tar.gz",
                "latest_checkpoint_path": "jobs/job-1/checkpoints/latest",
            },
        ),
        FakeResponse(204, {}),
        FakeResponse(204, {}),
        FakeResponse(200, {"status": "no_job_available"}),
    ]

    httpx_client_cm = Mock()
    httpx_client_cm.__enter__ = Mock(return_value=client)
    httpx_client_cm.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(
        "relaymd.worker.main.httpx.Client",
        lambda *args, **kwargs: httpx_client_cm,
    )

    run_worker(config)

    storage.download_file.assert_any_call("jobs/job-1/input/bundle.tar.gz", ANY)
    storage.download_file.assert_any_call("jobs/job-1/checkpoints/latest", ANY)
    storage.upload_file.assert_called_with(
        ANY,
        "jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoints/latest",
    )

    posted_paths = [call.args[0] for call in client.post.call_args_list]
    assert posted_paths == [
        "/workers/register",
        "/jobs/request",
        "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/checkpoint",
        "/jobs/6bd48968-0ecf-4205-9f59-091ec74e7f79/complete",
        "/jobs/request",
    ]

    heartbeat_thread.start.assert_called_once_with()
    heartbeat_stop_event.set.assert_called_once_with()
    heartbeat_thread.join.assert_called_once_with(timeout=5)


def test_detect_gpu_fallback_when_pynvml_fails(monkeypatch) -> None:
    def raising_module():
        raise RuntimeError("nvml unavailable")

    monkeypatch.setattr("relaymd.worker.main._get_pynvml_module", raising_module)

    from relaymd.worker.main import detect_gpu_info

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    assert (gpu_model, gpu_count, vram_gb) == ("unknown", 0, 0)
