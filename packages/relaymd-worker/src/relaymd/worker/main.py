from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any
from uuid import UUID

import httpx
from relaymd.models import JobAssigned, Platform, WorkerRegister
from relaymd.storage import StorageClient
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.heartbeat import HeartbeatThread

LOGGER = logging.getLogger(__name__)
ORCHESTRATOR_TIMEOUT_SECONDS = 30.0
DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS = 300
DEFAULT_CF_WORKER_URL = "https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev"
SIGTERM_CHECKPOINT_WAIT_SECONDS = 60
SIGTERM_CHECKPOINT_POLL_SECONDS = 2


@dataclass
class BundleExecutionConfig:
    command: list[str]
    checkpoint_glob_pattern: str


def _get_pynvml_module() -> ModuleType:
    import pynvml  # type: ignore[import-not-found]

    return pynvml


def detect_gpu_info() -> tuple[str, int, int]:
    try:
        pynvml = _get_pynvml_module()
        pynvml.nvmlInit()
        try:
            gpu_count = int(pynvml.nvmlDeviceGetCount())
            if gpu_count <= 0:
                return "unknown", 0, 0

            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            gpu_model = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_gb = int(memory_info.total / (1024**3))
            return gpu_model, gpu_count, vram_gb
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        LOGGER.exception("GPU detection failed; falling back to defaults")
        return "unknown", 0, 0


def _find_latest_checkpoint(workdir: Path, pattern: str) -> Path | None:
    candidates = [path for path in workdir.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_bundle_execution_config(bundle_root: Path) -> BundleExecutionConfig:
    candidate_paths = [
        bundle_root / "relaymd-worker.json",
        bundle_root / "relaymd-worker.toml",
        bundle_root / "config.json",
        bundle_root / "config.toml",
    ]

    for extension in ("*.json", "*.toml"):
        candidate_paths.extend(sorted(bundle_root.rglob(extension)))

    seen: set[Path] = set()
    for path in candidate_paths:
        if path in seen or not path.exists() or not path.is_file():
            continue
        seen.add(path)

        parsed = _parse_bundle_config(path)
        if parsed is None:
            continue

        command_raw = parsed.get("command")
        checkpoint_pattern = parsed.get("checkpoint_glob_pattern")
        if not command_raw or not checkpoint_pattern:
            continue

        if isinstance(command_raw, str):
            command = shlex.split(command_raw)
        elif isinstance(command_raw, list) and all(isinstance(item, str) for item in command_raw):
            command = command_raw
        else:
            continue

        if not command:
            continue
        return BundleExecutionConfig(
            command=command,
            checkpoint_glob_pattern=str(checkpoint_pattern),
        )

    raise RuntimeError("No valid worker bundle config found in input bundle")


def _parse_bundle_config(path: Path) -> dict[str, Any] | None:
    try:
        if path.suffix == ".json":
            with path.open("r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        elif path.suffix == ".toml":
            with path.open("rb") as file_obj:
                data = tomllib.load(file_obj)
        else:
            return None
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    return data


def _extract_input_bundle(bundle_file: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(bundle_file):
        with tarfile.open(bundle_file, "r:*") as archive:
            archive.extractall(destination, filter="data")
        return destination

    copied_path = destination / bundle_file.name
    copied_path.write_bytes(bundle_file.read_bytes())
    return destination


def _build_storage_client(config: WorkerConfig) -> StorageClient:
    cf_worker_url = os.getenv("CF_WORKER_URL", DEFAULT_CF_WORKER_URL)
    cf_bearer_token = os.getenv("DOWNLOAD_BEARER_TOKEN", config.relaymd_api_token)
    return StorageClient(
        b2_endpoint_url=config.b2_endpoint,
        b2_bucket_name=config.bucket_name,
        b2_access_key_id=config.b2_application_key_id,
        b2_secret_access_key=config.b2_application_key,
        cf_worker_url=cf_worker_url,
        cf_bearer_token=cf_bearer_token,
    )


def _wait_for_final_checkpoint(
    workdir: Path,
    checkpoint_glob_pattern: str,
    timeout_seconds: int = SIGTERM_CHECKPOINT_WAIT_SECONDS,
    poll_interval_seconds: int = SIGTERM_CHECKPOINT_POLL_SECONDS,
) -> Path | None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        checkpoint = _find_latest_checkpoint(workdir, checkpoint_glob_pattern)
        if checkpoint is not None:
            return checkpoint
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_seconds)


def _handle_sigterm(
    *,
    process: subprocess.Popen[Any],
    workdir: Path,
    checkpoint_glob_pattern: str,
    checkpoint_b2_key: str,
    storage: StorageClient,
    client: httpx.Client,
    job_id: UUID,
    worker_id: UUID,
    stop_event: threading.Event,
    heartbeat_thread: HeartbeatThread,
) -> None:
    LOGGER.info("Received SIGTERM; shutting down worker gracefully")
    process.terminate()

    final_checkpoint = _wait_for_final_checkpoint(workdir, checkpoint_glob_pattern)
    if final_checkpoint is None:
        LOGGER.warning("No final checkpoint found during SIGTERM shutdown for job %s", job_id)
    else:
        try:
            storage.upload_file(final_checkpoint, checkpoint_b2_key)
            checkpoint_response = client.post(
                f"/jobs/{job_id}/checkpoint",
                json={"checkpoint_path": checkpoint_b2_key},
            )
            checkpoint_response.raise_for_status()
        except Exception:
            LOGGER.exception("Failed to upload final checkpoint during SIGTERM")

    try:
        deregister_response = client.post(f"/workers/{worker_id}/deregister")
        deregister_response.raise_for_status()
    except Exception:
        LOGGER.exception("Failed to deregister worker during SIGTERM")

    stop_event.set()
    heartbeat_thread.join(timeout=5)
    sys.exit(0)


def run_worker(config: WorkerConfig) -> None:
    storage = _build_storage_client(config)
    checkpoint_poll_interval = int(
        os.getenv("CHECKPOINT_POLL_INTERVAL_SECONDS", str(DEFAULT_CHECKPOINT_POLL_INTERVAL_SECONDS))
    )

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    platform_raw = os.getenv("WORKER_PLATFORM", Platform.salad.value)
    try:
        platform = Platform(platform_raw)
    except ValueError:
        platform = Platform.salad

    headers = {"X-API-Token": config.relaymd_api_token}

    with httpx.Client(
        base_url=config.relaymd_orchestrator_url.rstrip("/"),
        headers=headers,
        timeout=ORCHESTRATOR_TIMEOUT_SECONDS,
    ) as client:
        register_response = client.post(
            "/workers/register",
            json=WorkerRegister(
                platform=platform,
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
            ).model_dump(mode="json"),
        )
        register_response.raise_for_status()
        worker_id = UUID(register_response.json()["worker_id"])

        while True:
            request_response = client.post("/jobs/request")
            request_response.raise_for_status()
            request_payload = request_response.json()

            if request_payload.get("status") == "no_job_available":
                LOGGER.info("No job available, worker exiting")
                return

            assignment = JobAssigned.model_validate(request_payload)
            checkpoint_b2_key = f"jobs/{assignment.job_id}/checkpoints/latest"

            with tempfile.TemporaryDirectory(prefix=f"relaymd-{assignment.job_id}-") as tmpdir:
                workdir = Path(tmpdir)

                input_bundle_path = workdir / Path(assignment.input_bundle_path).name
                storage.download_file(assignment.input_bundle_path, input_bundle_path)

                bundle_root = _extract_input_bundle(input_bundle_path, workdir / "bundle")

                if assignment.latest_checkpoint_path:
                    checkpoint_download_path = (
                        workdir / Path(assignment.latest_checkpoint_path).name
                    )
                    storage.download_file(
                        assignment.latest_checkpoint_path,
                        checkpoint_download_path,
                    )

                execution_config = _load_bundle_execution_config(bundle_root)
                heartbeat_stop_event = threading.Event()
                heartbeat_thread = HeartbeatThread(
                    orchestrator_url=config.relaymd_orchestrator_url,
                    worker_id=worker_id,
                    api_token=config.relaymd_api_token,
                    stop_event=heartbeat_stop_event,
                )
                heartbeat_thread.start()
                process_holder: dict[str, subprocess.Popen[Any] | None] = {"process": None}

                def _sigterm_handler(
                    signum: int,
                    frame: FrameType | None,
                    *,
                    workdir: Path = bundle_root,
                    checkpoint_glob_pattern: str = execution_config.checkpoint_glob_pattern,
                    checkpoint_path: str = checkpoint_b2_key,
                    job_id: UUID = assignment.job_id,
                    worker_id_local: UUID = worker_id,
                    stop_event: threading.Event = heartbeat_stop_event,
                    heartbeat: HeartbeatThread = heartbeat_thread,
                    process_ref: dict[str, subprocess.Popen[Any] | None] = process_holder,
                ) -> None:
                    _ = (signum, frame)
                    process = process_ref["process"]
                    if process is None:
                        try:
                            deregister_response = client.post(
                                f"/workers/{worker_id_local}/deregister"
                            )
                            deregister_response.raise_for_status()
                        except Exception:
                            LOGGER.exception(
                                "Failed to deregister worker during pre-launch SIGTERM"
                            )
                        stop_event.set()
                        heartbeat.join(timeout=5)
                        sys.exit(0)
                    _handle_sigterm(
                        process=process,
                        workdir=workdir,
                        checkpoint_glob_pattern=checkpoint_glob_pattern,
                        checkpoint_b2_key=checkpoint_path,
                        storage=storage,
                        client=client,
                        job_id=job_id,
                        worker_id=worker_id_local,
                        stop_event=stop_event,
                        heartbeat_thread=heartbeat,
                    )

                previous_sigterm_handler = signal.getsignal(signal.SIGTERM)
                signal.signal(signal.SIGTERM, _sigterm_handler)

                process_holder["process"] = subprocess.Popen(  # noqa: S603
                    execution_config.command,
                    cwd=bundle_root,
                )

                last_uploaded_mtime: float | None = None
                try:
                    while True:
                        process = process_holder["process"]
                        if process is None:
                            raise RuntimeError("subprocess missing after launch")
                        process_exit = process.poll()
                        latest_checkpoint = _find_latest_checkpoint(
                            bundle_root, execution_config.checkpoint_glob_pattern
                        )
                        if latest_checkpoint is not None:
                            current_mtime = latest_checkpoint.stat().st_mtime
                            if (
                                last_uploaded_mtime is None
                                or current_mtime > last_uploaded_mtime
                            ):
                                storage.upload_file(latest_checkpoint, checkpoint_b2_key)
                                checkpoint_response = client.post(
                                    f"/jobs/{assignment.job_id}/checkpoint",
                                    json={"checkpoint_path": checkpoint_b2_key},
                                )
                                checkpoint_response.raise_for_status()
                                last_uploaded_mtime = current_mtime

                        if process_exit is not None:
                            if process_exit == 0:
                                final_checkpoint = _find_latest_checkpoint(
                                    bundle_root, execution_config.checkpoint_glob_pattern
                                )
                                if final_checkpoint is not None:
                                    final_mtime = final_checkpoint.stat().st_mtime
                                    if (
                                        last_uploaded_mtime is None
                                        or final_mtime > last_uploaded_mtime
                                    ):
                                        storage.upload_file(final_checkpoint, checkpoint_b2_key)
                                        final_checkpoint_response = client.post(
                                            f"/jobs/{assignment.job_id}/checkpoint",
                                            json={"checkpoint_path": checkpoint_b2_key},
                                        )
                                        final_checkpoint_response.raise_for_status()

                                complete_response = client.post(
                                    f"/jobs/{assignment.job_id}/complete"
                                )
                                complete_response.raise_for_status()
                            else:
                                fail_response = client.post(f"/jobs/{assignment.job_id}/fail")
                                fail_response.raise_for_status()
                            break

                        time.sleep(checkpoint_poll_interval)
                finally:
                    signal.signal(signal.SIGTERM, previous_sigterm_handler)
                    process = process_holder["process"]
                    if process is not None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    heartbeat_stop_event.set()
                    heartbeat_thread.join(timeout=5)
