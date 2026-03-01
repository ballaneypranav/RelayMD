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
from relaymd.orchestrator.slurm import submit_slurm_job

logger = structlog.get_logger(__name__)

SubmitSlurmJobFn = Callable[[ClusterConfig, OrchestratorSettings], Awaitable[str]]


def slurm_provider_id(cluster_name: str, slurm_job_id: str) -> str:
    """Build the canonical provider_id for a SLURM-backed worker placeholder."""
    return f"{cluster_name}:{slurm_job_id}"


async def _query_live_slurm_job_ids(job_ids: list[str]) -> set[str]:
    """Ask squeue which of the given raw SLURM job IDs are still alive (PD or R).

    Returns the set of IDs that squeue reports; an empty set means none are alive
    OR squeue is not available (non-HPC environments).  Errors are swallowed so
    that the reaper never crashes the scheduler.
    """
    if not job_ids:
        return set()

    try:
        process = await asyncio.create_subprocess_exec(
            "squeue",
            "--jobs",
            ",".join(job_ids),
            "--noheader",
            "--format=%i",
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

    # provider_id format: "<cluster_name>:<raw_slurm_job_id>"
    # Extract the raw SLURM ID (part after the last ":") for squeue lookup.
    raw_id_to_placeholder: dict[str, Worker] = {}
    for p in placeholders:
        if p.provider_id and ":" in p.provider_id:
            raw_id = p.provider_id.rsplit(":", 1)[-1]
            raw_id_to_placeholder[raw_id] = p

    if not raw_id_to_placeholder:
        return 0

    live_job_ids = await _query_live_slurm_job_ids(list(raw_id_to_placeholder.keys()))

    dead_placeholders = [
        p for raw_id, p in raw_id_to_placeholder.items() if raw_id not in live_job_ids
    ]

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
            submitted = await service.submit_cluster_if_needed(cluster=cluster)
            if submitted:
                submissions += 1

    return submissions
