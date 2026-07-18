from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid4

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.services.cluster_provisioning_state_service import (
    ClusterProvisioningStateService,
)
from relaymd.orchestrator.slurm import SlurmSubmissionError, submit_slurm_job
from relaymd.orchestrator.worker_image_compatibility import (
    WorkerImageAvailability,
    queue_blocked_reason,
)

logger = structlog.get_logger(__name__)
_ALL_CLUSTERS_DISABLED_WARNING = (
    "Queued jobs are waiting, but all SLURM clusters are disabled for provisioning."
)
_ALL_CLUSTERS_DISABLED_WARNING_RATE_LIMIT = timedelta(minutes=5)
_last_all_clusters_disabled_warning_at: datetime | None = None

SubmitSlurmJobFn = Callable[..., Awaitable[str]]


class SlurmProviderJobStatus(NamedTuple):
    provider_state: str
    provider_state_raw: str
    provider_reason: str | None


class QueuedJobCandidate(NamedTuple):
    id: UUID
    created_at: datetime
    preferred_clusters_json: str | None
    worker_image_key: str


def _squeue_stderr_has_invalid_job_id(stderr_text: str) -> bool:
    normalized = stderr_text.strip().lower()
    return "invalid job id specified" in normalized or "invalid job id" in normalized


def _cluster_submission_log_fields(cluster: ClusterConfig) -> dict[str, object]:
    return {
        "cluster_name": cluster.name,
        "partition": cluster.partition,
        "account": cluster.account,
        "qos": cluster.qos,
        "gres": cluster.slurm_gres,
        "nodes": cluster.nodes,
        "ntasks": cluster.ntasks,
        "wall_time": cluster.wall_time,
        "memory": cluster.memory,
        "memory_per_gpu": cluster.memory_per_gpu,
        "ssh_host": cluster.ssh_host,
        "ssh_username": cluster.ssh_username,
        "ssh_port": cluster.ssh_port,
        "ssh_key_file": cluster.ssh_key_file,
        "submission_target": f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
    }


def slurm_provider_id(cluster_name: str, slurm_job_id: str) -> str:
    """Build the canonical provider_id for a SLURM-backed worker placeholder."""
    return f"{cluster_name}:{slurm_job_id}"


def pending_slurm_job_marker(cluster_name: str, slurm_job_id: str) -> str:
    """Return the marker string used to track a pending SLURM job."""
    return slurm_provider_id(cluster_name, slurm_job_id)


def _normalize_slurm_state(raw_state: str) -> str:
    normalized = raw_state.strip().upper()
    if normalized in {"PD", "PENDING", "CONFIGURING", "CF"}:
        return "pending"
    if normalized in {"R", "RUNNING"}:
        return "running"
    if normalized in {"CG", "COMPLETING"}:
        return "completing"
    return "unknown"


def _parse_squeue_output(stdout_text: str) -> dict[str, SlurmProviderJobStatus]:
    statuses: dict[str, SlurmProviderJobStatus] = {}
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        job_id: str
        raw_state: str
        reason: str | None
        parts = line.split("|", 2)
        if len(parts) == 3:
            job_id, raw_state, reason_text = (part.strip() for part in parts)
            reason = reason_text if reason_text not in {"", "(null)", "None"} else None
        else:
            # Legacy/defensive fallback if output includes only IDs.
            job_id, raw_state, reason = line, "UNKNOWN", None

        if not job_id:
            continue

        statuses[job_id] = SlurmProviderJobStatus(
            provider_state=_normalize_slurm_state(raw_state),
            provider_state_raw=raw_state,
            provider_reason=reason,
        )
    return statuses


async def _query_live_slurm_job_statuses(
    cluster: ClusterConfig, job_ids: list[str]
) -> dict[str, SlurmProviderJobStatus] | None:
    """Ask squeue for status of the given raw SLURM job IDs.

    Returns a mapping keyed by job ID. Empty mapping means no jobs are alive.
    Returns None when squeue status could not be determined (timeout/error).
    """
    if not job_ids:
        return {}

    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
    ]
    if cluster.ssh_port != 22:
        command.extend(["-p", str(cluster.ssh_port)])
    if cluster.ssh_key_file:
        command.extend(["-i", cluster.ssh_key_file])
    command.append(f"{cluster.ssh_username}@{cluster.ssh_host}")
    command.extend(
        [
            "squeue",
            "--jobs",
            ",".join(job_ids),
            "--noheader",
            "--format=%i\\|%T\\|%r",
        ]
    )

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            if process.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                if _squeue_stderr_has_invalid_job_id(stderr_text):
                    if len(job_ids) == 1:
                        logger.info(
                            "slurm_squeue_job_missing",
                            cluster_name=cluster.name,
                            slurm_job_id=job_ids[0],
                            submission_target=f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
                            stderr=stderr_text,
                        )
                        return {}

                    recovered_statuses: dict[str, SlurmProviderJobStatus] = {}
                    for job_id in job_ids:
                        single_job_status = await _query_live_slurm_job_statuses(cluster, [job_id])
                        if single_job_status is None:
                            return None
                        recovered_statuses.update(single_job_status)

                    logger.info(
                        "slurm_squeue_invalid_job_id_recovered_via_per_job_queries",
                        cluster_name=cluster.name,
                        requested_job_count=len(job_ids),
                        recovered_live_job_count=len(recovered_statuses),
                        submission_target=f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
                    )
                    return recovered_statuses

                logger.warning(
                    "slurm_squeue_query_nonzero_exit",
                    cluster_name=cluster.name,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    return_code=process.returncode,
                    stderr=stderr_text,
                    slurm_job_ids=job_ids,
                    submission_target=f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
                )
                return None
            return _parse_squeue_output(stdout.decode("utf-8", errors="replace"))
        except TimeoutError:
            if process is not None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(Exception):  # noqa: BLE001
                    await asyncio.wait_for(process.communicate(), timeout=1.0)
            logger.warning(
                "slurm_squeue_query_timeout",
                cluster_name=cluster.name,
                attempt=attempt,
                max_attempts=max_attempts,
                timeout_seconds=30.0,
                slurm_job_ids=job_ids,
                submission_target=f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
            )
            if attempt < max_attempts:
                continue
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "slurm_squeue_query_failed",
                cluster_name=cluster.name,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
                slurm_job_ids=job_ids,
                submission_target=f"{cluster.ssh_username}@{cluster.ssh_host}:{cluster.ssh_port}",
            )
            return None

    return None


class SlurmProvisioningService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: OrchestratorSettings,
        stale_cutoff: datetime,
        submit_job: SubmitSlurmJobFn = submit_slurm_job,
    ) -> None:
        self._session = session
        self._settings = settings
        self._stale_cutoff = stale_cutoff
        self._submit_job = submit_job

    @staticmethod
    def _preferred_clusters_json(preferred_clusters_json: str | None) -> list[str]:
        if not preferred_clusters_json:
            return []
        try:
            parsed = json.loads(preferred_clusters_json)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [name for item in parsed if (name := str(item).strip())]

    async def submit_cluster_if_needed(
        self, *, cluster: ClusterConfig, queued_jobs: list[QueuedJobCandidate]
    ) -> bool:
        queued_job = next(
            (
                job
                for job in queued_jobs
                if job.worker_image_key in cluster.worker_images
                and (
                    (
                        preferred_clusters := self._preferred_clusters_json(
                            job.preferred_clusters_json
                        )
                    )
                    == []
                    or cluster.name in preferred_clusters
                )
            ),
            None,
        )
        if queued_job is None:
            logger.info("provisioning_skipped_no_queued_jobs", cluster_name=cluster.name)
            return False

        logger.info(
            "provisioning_evaluated",
            cluster_name=cluster.name,
            job_id=str(queued_job.id),
            worker_image_key=queued_job.worker_image_key,
            strategy=cluster.strategy,
        )

        if cluster.strategy == "jit_threshold":
            now = datetime.now(UTC).replace(tzinfo=None)
            wait_time_hours = (now - queued_job.created_at).total_seconds() / 3600.0
            if wait_time_hours < cluster.jit_threshold_hours:
                logger.info(
                    "provisioning_skipped_jit_threshold_not_met",
                    cluster_name=cluster.name,
                    job_id=str(queued_job.id),
                    wait_time_hours=round(wait_time_hours, 2),
                    threshold_hours=cluster.jit_threshold_hours,
                )
                return False

            logger.info(
                "jit_threshold reached for cluster",
                cluster=cluster.name,
                oldest_job_id=str(queued_job.id),
                wait_time_hours=round(wait_time_hours, 2),
                threshold_hours=cluster.jit_threshold_hours,
            )

        if cluster.strategy != "continuous":
            # Don't submit if a live (active) HPC worker is already running.
            active_hpc_workers = (
                await self._session.exec(
                    select(Worker).where(
                        Worker.platform == Platform.hpc,
                        Worker.status == WorkerStatus.active,
                        Worker.worker_image_key == queued_job.worker_image_key,
                        col(Worker.provider_id).startswith(f"{cluster.name}:"),
                        col(Worker.last_heartbeat) >= self._stale_cutoff,
                    )
                )
            ).all()
            if active_hpc_workers:
                logger.info(
                    "provisioning_skipped_active_worker_exists",
                    cluster_name=cluster.name,
                    job_id=str(queued_job.id),
                    active_worker_count=len(active_hpc_workers),
                )
                return False

        # Don't exceed max_pending_jobs queued placeholders for this cluster.
        # Placeholders are identified by status=queued + provider_id prefix.
        cluster_prefix = f"{cluster.name}:"
        pending_workers = (
            await self._session.exec(
                select(Worker).where(
                    Worker.platform == Platform.hpc,
                    Worker.status == WorkerStatus.queued,
                    col(Worker.provider_id).startswith(cluster_prefix),
                    Worker.worker_image_key == queued_job.worker_image_key,
                )
            )
        ).all()
        if len(pending_workers) >= cluster.max_pending_jobs:
            logger.info(
                "provisioning_skipped_max_pending_reached",
                cluster_name=cluster.name,
                job_id=str(queued_job.id),
                pending_worker_count=len(pending_workers),
                max_pending_jobs=cluster.max_pending_jobs,
            )
            return False

        if not self._settings.infisical_token:
            logger.info(
                "provisioning_skipped_missing_infisical_token",
                cluster_name=cluster.name,
                job_id=str(queued_job.id),
            )
            return False

        logger.info(
            "slurm_submission_started", cluster_name=cluster.name, job_id=str(queued_job.id)
        )
        placeholder_id = uuid4()
        raw_slurm_id = await self._submit_job(
            cluster,
            self._settings,
            worker_id=placeholder_id,
            worker_image_key=queued_job.worker_image_key,
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        placeholder = Worker(
            id=placeholder_id,
            platform=Platform.hpc,
            gpu_model=cluster.gpu_type,
            gpu_count=cluster.gpu_count,
            vram_gb=0,
            worker_image_key=queued_job.worker_image_key,
            status=WorkerStatus.queued,
            provider_id=slurm_provider_id(cluster.name, raw_slurm_id),
            provider_state="submitted",
            last_heartbeat=now,
            registered_at=now,
        )
        self._session.add(placeholder)
        await self._session.commit()
        logger.info(
            "placeholder_worker_created",
            cluster_name=cluster.name,
            job_id=str(queued_job.id),
            provider_id=placeholder.provider_id,
            worker_id=str(placeholder.id),
            worker_image_key=queued_job.worker_image_key,
        )
        logger.info(
            "slurm_cluster_submission_succeeded",
            slurm_job_id=raw_slurm_id,
            provider_id=placeholder.provider_id,
            worker_id=str(placeholder.id),
            worker_image_key=queued_job.worker_image_key,
            **_cluster_submission_log_fields(cluster),
        )
        return True


async def reap_dead_slurm_placeholders(settings: OrchestratorSettings) -> int:
    """Delete queued placeholder Workers whose SLURM jobs are no longer alive.

    Handles the case where a SLURM job fails or is cancelled *before* the worker
    process starts and calls POST /workers/register.  Without this reaper, those
    placeholder rows accumulate and block future sbatch submissions once
    ``max_pending_jobs`` is reached.

    Returns the number of placeholders deleted.
    """
    if not settings.slurm_cluster_configs:
        return 0

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        placeholders = (
            await session.exec(
                select(Worker).where(
                    Worker.platform == Platform.hpc,
                    Worker.status == WorkerStatus.queued,
                )
            )
        ).all()

    if not placeholders:
        return 0

    from collections import defaultdict

    cluster_to_raw_ids: dict[str, dict[str, Worker]] = defaultdict(dict)
    for p in placeholders:
        if p.provider_id and ":" in p.provider_id:
            cluster_name, raw_id = p.provider_id.split(":", 1)
            cluster_to_raw_ids[cluster_name][raw_id] = p

    if not cluster_to_raw_ids:
        return 0

    cluster_configs = {c.name: c for c in settings.slurm_cluster_configs}
    dead_placeholders: list[tuple[Worker, str | None, str | None, str | None]] = []
    live_updates: dict[UUID, SlurmProviderJobStatus] = {}

    for cluster_name, raw_id_dict in cluster_to_raw_ids.items():
        cluster_config = cluster_configs.get(cluster_name)
        if not cluster_config:
            import structlog

            structlog.get_logger(__name__).warning(
                "slurm_cluster_config_missing_for_placeholders",
                cluster_name=cluster_name,
                placeholder_count=len(raw_id_dict),
            )
            for raw_id, placeholder in raw_id_dict.items():
                dead_placeholders.append((placeholder, "gone", "CLUSTER_CONFIG_MISSING", raw_id))
            continue

        raw_ids = list(raw_id_dict.keys())
        live_statuses = await _query_live_slurm_job_statuses(cluster_config, raw_ids)
        if live_statuses is None:
            logger.warning(
                "slurm_placeholder_reap_skipped_due_to_status_query_failure",
                cluster_name=cluster_name,
                placeholder_count=len(raw_id_dict),
            )
            continue

        for raw_id, p in raw_id_dict.items():
            status = live_statuses.get(raw_id)
            if status is None:
                dead_placeholders.append((p, "gone", "GONE", raw_id))
                continue
            live_updates[p.id] = status

    now = datetime.now(UTC).replace(tzinfo=None)
    async with sessionmaker() as session:
        for worker_id, status in live_updates.items():
            fresh = await session.get(Worker, worker_id)
            if fresh is None:
                continue
            fresh.provider_state = status.provider_state
            fresh.provider_state_raw = status.provider_state_raw
            fresh.provider_reason = status.provider_reason
            fresh.provider_last_checked_at = now
            session.add(fresh)
        await session.commit()

    if not dead_placeholders:
        return 0

    async with sessionmaker() as session:
        for placeholder, state, raw_state, raw_id in dead_placeholders:
            logger.info(
                "reaping_dead_slurm_placeholder",
                provider_id=placeholder.provider_id,
                worker_id=str(placeholder.id),
                provider_state=state,
                provider_state_raw=raw_state,
                slurm_job_id=raw_id,
            )
            fresh = await session.get(Worker, placeholder.id)
            if fresh is not None:
                await session.delete(fresh)
        await session.commit()

    return len(dead_placeholders)


async def submit_pending_slurm_jobs(
    settings: OrchestratorSettings,
    *,
    submit_job: SubmitSlurmJobFn = submit_slurm_job,
) -> int:
    if not settings.slurm_cluster_configs:
        return 0

    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        seconds=settings.heartbeat_timeout_multiplier * settings.heartbeat_interval_seconds
    )
    sessionmaker = get_sessionmaker()
    submissions = 0
    async with sessionmaker() as session:
        cluster_state_service = ClusterProvisioningStateService(session)
        enabled_map = await cluster_state_service.get_enabled_map(settings.slurm_cluster_configs)
        enabled_clusters = [
            cluster
            for cluster in settings.slurm_cluster_configs
            if enabled_map.get(cluster.name, True)
        ]

        if not enabled_clusters:
            queued_job = (
                await session.exec(select(Job).where(Job.status == JobStatus.queued))
            ).first()
            if queued_job is not None:
                _emit_all_clusters_disabled_warning()

        queued_jobs = (
            await session.exec(
                select(Job).where(col(Job.status) == JobStatus.queued).order_by(col(Job.created_at))
            )
        ).all()
        queued_job_candidates = [
            QueuedJobCandidate(
                id=job.id,
                created_at=job.created_at,
                preferred_clusters_json=job.preferred_clusters_json,
                worker_image_key=job.worker_image_key,
            )
            for job in queued_jobs
        ]
        for job in queued_jobs:
            preferred_clusters: list[str] = []
            if job.preferred_clusters_json:
                try:
                    parsed = json.loads(job.preferred_clusters_json)
                    if isinstance(parsed, list):
                        preferred_clusters = [
                            name for item in parsed if (name := str(item).strip())
                        ]
                except Exception:
                    preferred_clusters = []
            reason = queue_blocked_reason(
                preferred_clusters=preferred_clusters,
                worker_image_key=job.worker_image_key,
                availability=WorkerImageAvailability(
                    clusters=settings.slurm_cluster_configs,
                    enabled_map=enabled_map,
                    salad_worker_image_key=settings.salad_worker_image_key
                    or settings.default_worker_image,
                    salad_enabled=settings.salad_container_group is not None,
                ),
            )
            if job.queue_blocked_reason != reason:
                job.queue_blocked_reason = reason
                job.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(job)
        await session.commit()

        service = SlurmProvisioningService(
            session,
            settings=settings,
            stale_cutoff=stale_cutoff,
            submit_job=submit_job,
        )
        for cluster in enabled_clusters:
            try:
                submitted = await service.submit_cluster_if_needed(
                    cluster=cluster, queued_jobs=queued_job_candidates
                )
            except SlurmSubmissionError as exc:
                try:
                    await session.rollback()
                except Exception as rollback_exc:  # noqa: BLE001
                    logger.exception(
                        "slurm_cluster_submission_rollback_failed",
                        error=str(rollback_exc),
                        original_error=str(exc),
                        **_cluster_submission_log_fields(cluster),
                    )
                    raise
                logger.error(
                    "slurm_cluster_submission_failed",
                    error=str(exc),
                    **exc.to_log_fields(),
                )
                continue
            except Exception as exc:  # noqa: BLE001
                try:
                    await session.rollback()
                except Exception as rollback_exc:  # noqa: BLE001
                    logger.exception(
                        "slurm_cluster_submission_rollback_failed",
                        error=str(rollback_exc),
                        original_error=str(exc),
                        **_cluster_submission_log_fields(cluster),
                    )
                    raise
                logger.exception(
                    "slurm_cluster_submission_unexpected_error",
                    error=str(exc),
                    **_cluster_submission_log_fields(cluster),
                )
                continue
            if submitted:
                submissions += 1

    return submissions


def _emit_all_clusters_disabled_warning() -> None:
    global _last_all_clusters_disabled_warning_at
    now = datetime.now(UTC)
    if (
        _last_all_clusters_disabled_warning_at is not None
        and now - _last_all_clusters_disabled_warning_at < _ALL_CLUSTERS_DISABLED_WARNING_RATE_LIMIT
    ):
        return
    _last_all_clusters_disabled_warning_at = now
    logger.warning(
        "all_slurm_clusters_disabled_with_queued_jobs",
        warning=_ALL_CLUSTERS_DISABLED_WARNING,
    )


def get_runtime_scheduler_warnings(settings: OrchestratorSettings) -> list[str]:
    if not settings.slurm_cluster_configs:
        return []
    if _last_all_clusters_disabled_warning_at is None:
        return []
    if (
        datetime.now(UTC) - _last_all_clusters_disabled_warning_at
        > _ALL_CLUSTERS_DISABLED_WARNING_RATE_LIMIT
    ):
        return []
    return [_ALL_CLUSTERS_DISABLED_WARNING]
