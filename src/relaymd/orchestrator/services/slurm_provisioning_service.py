from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Platform, Worker, WorkerStatus
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.slurm import SlurmSubmissionError, submit_slurm_job

logger = structlog.get_logger(__name__)

SubmitSlurmJobFn = Callable[[ClusterConfig, OrchestratorSettings], Awaitable[str]]


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


async def _query_live_slurm_job_ids(cluster: ClusterConfig, job_ids: list[str]) -> set[str]:
    """Ask squeue which of the given raw SLURM job IDs are still alive (PD or R).

    Returns the set of IDs that squeue reports; an empty set means none are alive
    OR squeue is not available (non-HPC environments).  Errors are swallowed so
    that the reaper never crashes the scheduler.
    """
    if not job_ids:
        return set()

    command = [
        "ssh",
        "-q",
        "-o",
        "BatchMode=yes",
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
            "--format=%i",
        ]
    )

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        with suppress(Exception):
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30.0)
            return {
                line.strip()
                for line in stdout.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            }
    except Exception:  # noqa: BLE001
        pass
    return set()


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

    async def submit_cluster_if_needed(self, *, cluster: ClusterConfig) -> bool:
        queued_job = (
            await self._session.exec(
                select(Job)
                .where(Job.status == JobStatus.queued)
                .order_by(col(Job.created_at))
                .limit(1)
            )
        ).first()
        if queued_job is None:
            return False

        if cluster.strategy == "jit_threshold":
            now = datetime.now(UTC).replace(tzinfo=None)
            wait_time_hours = (now - queued_job.created_at).total_seconds() / 3600.0
            if wait_time_hours < cluster.jit_threshold_hours:
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
                        col(Worker.last_heartbeat) >= self._stale_cutoff,
                    )
                )
            ).all()
            if active_hpc_workers:
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
                )
            )
        ).all()
        if len(pending_workers) >= cluster.max_pending_jobs:
            return False

        if not self._settings.infisical_token:
            return False

        raw_slurm_id = await self._submit_job(cluster, self._settings)
        now = datetime.now(UTC).replace(tzinfo=None)
        placeholder = Worker(
            id=uuid4(),
            platform=Platform.hpc,
            gpu_model=cluster.gpu_type,
            gpu_count=cluster.gpu_count,
            vram_gb=0,
            status=WorkerStatus.queued,
            provider_id=slurm_provider_id(cluster.name, raw_slurm_id),
            last_heartbeat=now,
            registered_at=now,
        )
        self._session.add(placeholder)
        await self._session.commit()
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
    dead_placeholders: list[Worker] = []

    for cluster_name, raw_id_dict in cluster_to_raw_ids.items():
        cluster_config = cluster_configs.get(cluster_name)
        if not cluster_config:
            import structlog

            structlog.get_logger(__name__).warning(
                "slurm_cluster_config_missing_for_placeholders",
                cluster_name=cluster_name,
                placeholder_count=len(raw_id_dict),
            )
            dead_placeholders.extend(raw_id_dict.values())
            continue

        raw_ids = list(raw_id_dict.keys())
        live_job_ids = await _query_live_slurm_job_ids(cluster_config, raw_ids)

        for raw_id, p in raw_id_dict.items():
            if raw_id not in live_job_ids:
                dead_placeholders.append(p)

    if not dead_placeholders:
        return 0

    async with sessionmaker() as session:
        for placeholder in dead_placeholders:
            logger.info(
                "reaping_dead_slurm_placeholder",
                provider_id=placeholder.provider_id,
                worker_id=str(placeholder.id),
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
        service = SlurmProvisioningService(
            session,
            settings=settings,
            stale_cutoff=stale_cutoff,
            submit_job=submit_job,
        )
        for cluster in settings.slurm_cluster_configs:
            try:
                submitted = await service.submit_cluster_if_needed(cluster=cluster)
            except SlurmSubmissionError as exc:
                with suppress(Exception):
                    await session.rollback()
                logger.error(
                    "slurm_cluster_submission_failed",
                    error=str(exc),
                    **exc.to_log_fields(),
                )
                continue
            except Exception as exc:  # noqa: BLE001
                with suppress(Exception):
                    await session.rollback()
                logger.exception(
                    "slurm_cluster_submission_unexpected_error",
                    error=str(exc),
                    **_cluster_submission_log_fields(cluster),
                )
                continue
            if submitted:
                submissions += 1

    return submissions
