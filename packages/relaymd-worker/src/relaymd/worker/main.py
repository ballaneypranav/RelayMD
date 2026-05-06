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
    checkpoint_poll_interval_seconds: int | None = None
    progress_glob_patterns: list[str] | None = None
    startup_progress_timeout_seconds: int | None = None
    progress_timeout_seconds: int | None = None
    max_runtime_seconds: int | None = None
    fatal_log_path: str | None = None
    fatal_log_patterns: list[str] | None = None


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


def detect_openmm_platforms() -> list[str]:
    try:
        from openmm import Platform  # type: ignore[import-not-found]
    except Exception:
        LOG.exception("openmm_preflight_import_failed")
        return []

    try:
        return [Platform.getPlatform(i).getName() for i in range(Platform.getNumPlatforms())]
    except Exception:
        LOG.exception("openmm_preflight_platform_probe_failed")
        return []


def _find_latest_checkpoint(workdir: Path, pattern: str) -> Path | None:
    candidates = [path for path in workdir.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _checkpoint_mtime(checkpoint: Path | None) -> float | None:
    if checkpoint is None:
        return None
    try:
        return checkpoint.stat().st_mtime
    except OSError:
        return None


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
        bundle_interval = _optional_positive_int(
            parsed,
            "checkpoint_poll_interval_seconds",
        )
        startup_progress_timeout_seconds = _optional_positive_int(
            parsed,
            "startup_progress_timeout_seconds",
        )
        progress_timeout_seconds = _optional_positive_int(
            parsed,
            "progress_timeout_seconds",
        )
        max_runtime_seconds = _optional_positive_int(parsed, "max_runtime_seconds")
        progress_glob_patterns = _optional_string_list(parsed, "progress_glob_pattern")
        fatal_log_path = _optional_string(parsed, "fatal_log_path")
        fatal_log_patterns = _optional_string_list(parsed, "fatal_log_patterns")

        return BundleExecutionConfig(
            command=command,
            checkpoint_glob_pattern=str(checkpoint_pattern),
            checkpoint_poll_interval_seconds=bundle_interval,
            progress_glob_patterns=progress_glob_patterns,
            startup_progress_timeout_seconds=startup_progress_timeout_seconds,
            progress_timeout_seconds=progress_timeout_seconds,
            max_runtime_seconds=max_runtime_seconds,
            fatal_log_path=fatal_log_path,
            fatal_log_patterns=fatal_log_patterns,
        )

    raise RuntimeError("No valid worker bundle config found in input bundle")


def _optional_positive_int(parsed: dict[str, Any], key: str) -> int | None:
    value = parsed.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"Invalid {key} in bundle config")
    return value


def _optional_string(parsed: dict[str, Any], key: str) -> str | None:
    value = parsed.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid {key} in bundle config")
    return value


def _optional_string_list(parsed: dict[str, Any], key: str) -> list[str] | None:
    value = parsed.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            raise RuntimeError(f"Invalid {key} in bundle config")
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise RuntimeError(f"Invalid {key} in bundle config")


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
            try:
                archive.extractall(destination, filter="data")
            except TypeError as err:
                destination_abs = destination.resolve()
                for member in archive.getmembers():
                    if member.issym() or member.islnk():
                        raise RuntimeError(
                            "Input bundle must not contain symlinks or hard links"
                        ) from err
                    member_target = (destination / member.name).resolve()
                    if (
                        member_target != destination_abs
                        and destination_abs not in member_target.parents
                    ):
                        raise RuntimeError("Input bundle contains path traversal entries") from err
                archive.extractall(destination)
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
    min_checkpoint_mtime: float | None = None,
) -> Path | None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        checkpoint = _find_latest_checkpoint(workdir, checkpoint_glob_pattern)
        checkpoint_mtime = _checkpoint_mtime(checkpoint)
        if (
            checkpoint is not None
            and checkpoint_mtime is not None
            and (min_checkpoint_mtime is None or checkpoint_mtime > min_checkpoint_mtime)
        ):
            return checkpoint
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_seconds)


def _upload_checkpoint(
    context: WorkerContext,
    *,
    logger,
    checkpoint: Path,
    checkpoint_b2_key: str,
    job_id: UUID,
) -> float:
    checkpoint_stat = checkpoint.stat()
    logger.info(
        "checkpoint_upload_started",
        checkpoint_path=str(checkpoint),
        checkpoint_b2_key=checkpoint_b2_key,
        checkpoint_size_bytes=checkpoint_stat.st_size,
        checkpoint_mtime=checkpoint_stat.st_mtime,
    )
    try:
        context.storage.upload_file(checkpoint, checkpoint_b2_key)
        logger.info(
            "checkpoint_upload_succeeded",
            checkpoint_path=str(checkpoint),
            checkpoint_b2_key=checkpoint_b2_key,
            checkpoint_size_bytes=checkpoint_stat.st_size,
            checkpoint_mtime=checkpoint_stat.st_mtime,
        )
        context.gateway.report_checkpoint(
            job_id=job_id,
            checkpoint_path=checkpoint_b2_key,
        )
        logger.info(
            "checkpoint_report_succeeded",
            checkpoint_path=str(checkpoint),
            checkpoint_b2_key=checkpoint_b2_key,
            checkpoint_size_bytes=checkpoint_stat.st_size,
            checkpoint_mtime=checkpoint_stat.st_mtime,
        )
        return checkpoint_stat.st_mtime
    except Exception:
        logger.exception(
            "checkpoint_upload_failed",
            checkpoint_path=str(checkpoint),
            checkpoint_b2_key=checkpoint_b2_key,
            checkpoint_size_bytes=checkpoint_stat.st_size,
            checkpoint_mtime=checkpoint_stat.st_mtime,
        )
        raise


def _fatal_log_artifact(bundle_root: Path, execution_config: BundleExecutionConfig) -> Path | None:
    if execution_config.fatal_log_path is None:
        return None

    path = bundle_root / execution_config.fatal_log_path
    if not path.is_file():
        return None
    return path


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
            progress_glob_patterns=execution_config.progress_glob_patterns,
            startup_progress_timeout_seconds=(execution_config.startup_progress_timeout_seconds),
            progress_timeout_seconds=execution_config.progress_timeout_seconds,
            max_runtime_seconds=execution_config.max_runtime_seconds,
            fatal_log_path=execution_config.fatal_log_path,
            fatal_log_patterns=execution_config.fatal_log_patterns,
        )
        execution.start()

        last_uploaded_mtime: float | None = None
        effective_checkpoint_poll_interval_seconds = (
            execution_config.checkpoint_poll_interval_seconds
            if execution_config.checkpoint_poll_interval_seconds is not None
            else context.checkpoint_poll_interval_seconds
        )
        job_log.info(
            "checkpoint_poll_interval_resolved",
            checkpoint_poll_interval_seconds=effective_checkpoint_poll_interval_seconds,
            source=(
                "bundle"
                if execution_config.checkpoint_poll_interval_seconds is not None
                else "runtime_default"
            ),
        )
        checkpoint_poll_interval_seconds = float(effective_checkpoint_poll_interval_seconds)
        next_checkpoint_poll_time = time.monotonic()
        try:
            while True:
                if context.shutdown_event.is_set():
                    job_log.info("shutdown_requested_terminating_job")
                    baseline_mtime = last_uploaded_mtime
                    latest_checkpoint_before_shutdown = execution.latest_checkpoint()
                    latest_mtime_before_shutdown = _checkpoint_mtime(
                        latest_checkpoint_before_shutdown
                    )
                    if latest_mtime_before_shutdown is not None and (
                        baseline_mtime is None or latest_mtime_before_shutdown > baseline_mtime
                    ):
                        baseline_mtime = latest_mtime_before_shutdown

                    execution.request_terminate()
                    final_checkpoint = _wait_for_final_checkpoint(
                        bundle_root,
                        execution_config.checkpoint_glob_pattern,
                        timeout_seconds=context.sigterm_checkpoint_wait_seconds,
                        poll_interval_seconds=context.sigterm_checkpoint_poll_seconds,
                        min_checkpoint_mtime=baseline_mtime,
                    )
                    if (
                        final_checkpoint is None
                        and last_uploaded_mtime is None
                        and assignment.latest_checkpoint_path is None
                        and latest_checkpoint_before_shutdown is not None
                    ):
                        final_checkpoint = latest_checkpoint_before_shutdown

                    if final_checkpoint is not None:
                        final_mtime = _checkpoint_mtime(final_checkpoint)
                        if last_uploaded_mtime is None or (
                            final_mtime is not None and final_mtime > last_uploaded_mtime
                        ):
                            last_uploaded_mtime = _upload_checkpoint(
                                context,
                                logger=job_log,
                                checkpoint=final_checkpoint,
                                checkpoint_b2_key=checkpoint_b2_key,
                                job_id=assignment.job_id,
                            )
                    elif baseline_mtime is not None:
                        job_log.info(
                            "shutdown_no_newer_checkpoint_found",
                            checkpoint_b2_key=checkpoint_b2_key,
                            baseline_mtime=baseline_mtime,
                        )
                    execution.wait(timeout_seconds=context.sigterm_process_wait_seconds)
                    return

                now = time.monotonic()
                if now >= next_checkpoint_poll_time:
                    for checkpoint in execution.iter_new_checkpoints():
                        last_uploaded_mtime = _upload_checkpoint(
                            context,
                            logger=job_log,
                            checkpoint=checkpoint,
                            checkpoint_b2_key=checkpoint_b2_key,
                            job_id=assignment.job_id,
                        )
                    if checkpoint_poll_interval_seconds > 0:
                        next_checkpoint_poll_time = now + checkpoint_poll_interval_seconds
                    else:
                        next_checkpoint_poll_time = now

                supervision_failure_method = getattr(execution, "supervision_failure", None)
                if supervision_failure_method is not None:
                    supervision_failure = supervision_failure_method(now=now)
                    if supervision_failure is not None:
                        job_log.warning(
                            "job_supervision_failed",
                            reason=supervision_failure.reason,
                            detail=supervision_failure.detail,
                        )
                        execution.request_terminate()
                        if (
                            execution.wait(
                                timeout_seconds=context.sigterm_process_wait_seconds,
                            )
                            is None
                        ):
                            job_log.warning(
                                "job_supervision_killing_process",
                                reason=supervision_failure.reason,
                            )
                            execution.kill()
                            execution.wait(timeout_seconds=5)

                        final_checkpoint = (
                            _fatal_log_artifact(bundle_root, execution_config)
                            if supervision_failure.reason == "fatal_log_match"
                            else execution.latest_checkpoint()
                        )
                        if final_checkpoint is not None:
                            _upload_checkpoint(
                                context,
                                logger=job_log,
                                checkpoint=final_checkpoint,
                                checkpoint_b2_key=checkpoint_b2_key,
                                job_id=assignment.job_id,
                            )
                        context.gateway.fail_job(job_id=assignment.job_id)
                        return

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
                        logger=job_log,
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
    import sys

    runtime_settings = WorkerRuntimeSettings()
    if not runtime_settings.axiom_token.strip():
        LOG.error(
            "axiom_token_missing",
            message=(
                "AXIOM_TOKEN is required but not set. "
                "Set it via AXIOM_TOKEN env var or ensure Infisical is reachable during bootstrap."
            ),
        )
        sys.exit(1)
    storage = _build_storage_client(config, runtime_settings)
    orchestrator_url = config.relaymd_orchestrator_url.rstrip("/")

    gpu_model, gpu_count, vram_gb = detect_gpu_info()
    openmm_platforms = detect_openmm_platforms()
    LOG.info(
        "openmm_preflight_platforms_detected",
        openmm_platforms=openmm_platforms,
        openmm_cuda_available="CUDA" in openmm_platforms,
    )
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
