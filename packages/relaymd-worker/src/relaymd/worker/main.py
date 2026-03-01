from __future__ import annotations

import json
import os
import shlex
import signal
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

from relaymd_api_client.models.job_assigned import JobAssigned as ApiJobAssigned
from relaymd_api_client.models.no_job_available import NoJobAvailable as ApiNoJobAvailable
from relaymd_api_client.models.platform import Platform as ApiPlatform

from relaymd.models import Platform
from relaymd.storage import StorageClient
from relaymd.worker.bootstrap import WorkerConfig
from relaymd.worker.config import WorkerRuntimeSettings
from relaymd.worker.context import WorkerContext
from relaymd.worker.gateway import ApiOrchestratorGateway
from relaymd.worker.heartbeat import HeartbeatThread
from relaymd.worker.job_execution import JobExecution
from relaymd.worker.logging import get_logger

LOG = get_logger(__name__)
PROCESS_EXIT_POLL_INTERVAL_SECONDS = 2.0


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
        LOG.exception("gpu_detection_failed_falling_back_to_defaults")
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


def _build_storage_client(
    config: WorkerConfig,
    runtime_settings: WorkerRuntimeSettings,
) -> StorageClient:
    cf_bearer_token = (
        config.download_bearer_token or runtime_settings.cf_bearer_token or config.relaymd_api_token
    )
    return StorageClient(
        b2_endpoint_url=config.b2_endpoint,
        b2_bucket_name=config.bucket_name,
        b2_access_key_id=config.b2_application_key_id,
        b2_secret_access_key=config.b2_application_key,
        cf_worker_url=runtime_settings.cf_worker_url,
        cf_bearer_token=cf_bearer_token,
    )


def _wait_for_final_checkpoint(
    workdir: Path,
    checkpoint_glob_pattern: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> Path | None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        checkpoint = _find_latest_checkpoint(workdir, checkpoint_glob_pattern)
        if checkpoint is not None:
            return checkpoint
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_seconds)


def _upload_checkpoint(
    context: WorkerContext,
    *,
    checkpoint: Path,
    checkpoint_b2_key: str,
    job_id: UUID,
) -> float:
    context.storage.upload_file(checkpoint, checkpoint_b2_key)
    context.gateway.report_checkpoint(
        job_id=job_id,
        checkpoint_path=checkpoint_b2_key,
    )
    return checkpoint.stat().st_mtime


def _run_assigned_job(
    *,
    context: WorkerContext,
    assignment: ApiJobAssigned,
) -> None:
    job_log = context.logger.bind(job_id=str(assignment.job_id))
    checkpoint_b2_key = f"jobs/{assignment.job_id}/checkpoints/latest"

    with tempfile.TemporaryDirectory(prefix=f"relaymd-{assignment.job_id}-") as tmpdir:
        workdir = Path(tmpdir)
        input_bundle_path = workdir / Path(assignment.input_bundle_path).name
        context.storage.download_file(assignment.input_bundle_path, input_bundle_path)

        bundle_root = _extract_input_bundle(input_bundle_path, workdir / "bundle")

        if assignment.latest_checkpoint_path:
            checkpoint_download_path = workdir / Path(assignment.latest_checkpoint_path).name
            context.storage.download_file(
                assignment.latest_checkpoint_path,
                checkpoint_download_path,
            )

        execution_config = _load_bundle_execution_config(bundle_root)
        execution = JobExecution(
            command=execution_config.command,
            workdir=bundle_root,
            checkpoint_glob_pattern=execution_config.checkpoint_glob_pattern,
            checkpoint_b2_key=checkpoint_b2_key,
        )
        execution.start()

        last_uploaded_mtime: float | None = None
        checkpoint_poll_interval_seconds = float(context.checkpoint_poll_interval_seconds)
        next_checkpoint_poll_time = time.monotonic()
        try:
            while True:
                if context.shutdown_event.is_set():
                    job_log.info("shutdown_requested_terminating_job")
                    execution.request_terminate()
                    final_checkpoint = _wait_for_final_checkpoint(
                        bundle_root,
                        execution_config.checkpoint_glob_pattern,
                        timeout_seconds=context.sigterm_checkpoint_wait_seconds,
                        poll_interval_seconds=context.sigterm_checkpoint_poll_seconds,
                    )
                    if final_checkpoint is not None:
                        last_uploaded_mtime = _upload_checkpoint(
                            context,
                            checkpoint=final_checkpoint,
                            checkpoint_b2_key=checkpoint_b2_key,
                            job_id=assignment.job_id,
                        )
                    execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                    return

                now = time.monotonic()
                if now >= next_checkpoint_poll_time:
                    for checkpoint in execution.iter_new_checkpoints():
                        last_uploaded_mtime = _upload_checkpoint(
                            context,
                            checkpoint=checkpoint,
                            checkpoint_b2_key=checkpoint_b2_key,
                            job_id=assignment.job_id,
                        )
                    if checkpoint_poll_interval_seconds > 0:
                        next_checkpoint_poll_time = now + checkpoint_poll_interval_seconds
                    else:
                        next_checkpoint_poll_time = now

                process_exit = execution.poll_exit_code()
                if process_exit is not None:
                    break

                if checkpoint_poll_interval_seconds <= 0:
                    wait_timeout = 0.0
                else:
                    until_next_checkpoint_poll = max(0.0, next_checkpoint_poll_time - now)
                    wait_timeout = min(
                        PROCESS_EXIT_POLL_INTERVAL_SECONDS,
                        until_next_checkpoint_poll,
                    )
                context.shutdown_event.wait(timeout=wait_timeout)

            final_checkpoint = execution.latest_checkpoint()
            if final_checkpoint is not None:
                final_mtime = final_checkpoint.stat().st_mtime
                if last_uploaded_mtime is None or final_mtime > last_uploaded_mtime:
                    _upload_checkpoint(
                        context,
                        checkpoint=final_checkpoint,
                        checkpoint_b2_key=checkpoint_b2_key,
                        job_id=assignment.job_id,
                    )

            result = execution.result()
            if result.status == "completed":
                context.gateway.complete_job(job_id=assignment.job_id)
            elif result.status == "failed":
                context.gateway.fail_job(job_id=assignment.job_id)
        finally:
            if execution.is_running():
                job_log.warning("job_execution_cleanup_terminating_process")
                execution.request_terminate()
                if execution.wait(timeout_seconds=context.sigterm_process_wait_seconds) is None:
                    job_log.warning("job_execution_cleanup_killing_process")
                    execution.kill()
                    execution.wait(timeout_seconds=5)


def run_worker(config: WorkerConfig) -> None:
    runtime_settings = WorkerRuntimeSettings()
    storage = _build_storage_client(config, runtime_settings)
    orchestrator_url = config.relaymd_orchestrator_url.rstrip("/")

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    platform_raw = runtime_settings.worker_platform
    try:
        platform = Platform(platform_raw)
    except ValueError:
        platform = Platform.salad

    shutdown_event = threading.Event()
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

    def _sigterm_handler(signum: int, frame: FrameType | None) -> None:
        _ = (signum, frame)
        LOG.info("sigterm_received_requesting_shutdown")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _sigterm_handler)

    worker_id: UUID | None = None
    heartbeat_thread: HeartbeatThread | None = None

    try:
        LOG.info(
            "register_worker_target_resolved",
            orchestrator_url=orchestrator_url,
            register_endpoint=f"{orchestrator_url}/workers/register",
            timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
            max_attempts=runtime_settings.orchestrator_register_max_attempts,
        )
        with ApiOrchestratorGateway(
            orchestrator_url=orchestrator_url,
            api_token=config.relaymd_api_token,
            logger=LOG,
            timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
            register_worker_max_attempts=runtime_settings.orchestrator_register_max_attempts,
        ) as gateway:
            provider_id = None
            if platform == Platform.hpc:
                cluster_name = os.environ.get("RELAYMD_CLUSTER_NAME")
                slurm_job_id = os.environ.get("SLURM_JOB_ID")
                if cluster_name and slurm_job_id:
                    provider_id = f"{cluster_name}:{slurm_job_id}"

            worker_id = gateway.register_worker(
                platform=ApiPlatform(platform.value),
                gpu_model=gpu_model,
                gpu_count=gpu_count,
                vram_gb=vram_gb,
                provider_id=provider_id,
            )
            worker_log = LOG.bind(worker_id=str(worker_id))

            heartbeat_thread = HeartbeatThread(
                orchestrator_url=orchestrator_url,
                worker_id=worker_id,
                api_token=config.relaymd_api_token,
                interval_seconds=runtime_settings.heartbeat_interval_seconds,
                timeout_seconds=runtime_settings.orchestrator_timeout_seconds,
                stop_event=shutdown_event,
            )
            heartbeat_thread.start()

            context = WorkerContext(
                gateway=gateway,
                storage=storage,
                shutdown_event=shutdown_event,
                checkpoint_poll_interval_seconds=runtime_settings.checkpoint_poll_interval_seconds,
                sigterm_checkpoint_wait_seconds=runtime_settings.sigterm_checkpoint_wait_seconds,
                sigterm_checkpoint_poll_seconds=runtime_settings.sigterm_checkpoint_poll_seconds,
                sigterm_process_wait_seconds=runtime_settings.sigterm_process_wait_seconds,
                logger=worker_log,
            )

            idle_start_time: float | None = None

            while not shutdown_event.is_set():
                request_response = gateway.request_job(worker_id=worker_id)
                if isinstance(request_response, ApiNoJobAvailable):
                    if runtime_settings.idle_strategy == "immediate_exit":
                        worker_log.info("no_job_available_worker_exit")
                        break

                    if idle_start_time is None:
                        idle_start_time = time.monotonic()
                        worker_log.info("entering_idle_poll")

                    if time.monotonic() - idle_start_time >= runtime_settings.idle_poll_max_seconds:
                        worker_log.info("idle_timeout_reached")
                        break

                    shutdown_event.wait(timeout=runtime_settings.idle_poll_interval_seconds)
                    continue

                if idle_start_time is not None:
                    worker_log.info("job_found_during_poll")
                    idle_start_time = None

                _run_assigned_job(context=context, assignment=request_response)

            shutdown_event.set()
            if worker_id is not None:
                gateway.deregister_worker(worker_id=worker_id)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)
        shutdown_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=5)
