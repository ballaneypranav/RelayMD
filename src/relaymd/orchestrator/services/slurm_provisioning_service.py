from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Platform, Worker
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.slurm import submit_slurm_job

SubmitSlurmJobFn = Callable[[ClusterConfig, OrchestratorSettings], Awaitable[str]]


def pending_slurm_job_marker(cluster_name: str, slurm_job_id: str) -> str:
    return f"{cluster_name}:{slurm_job_id}"


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
            await self._session.exec(select(Job).where(Job.status == JobStatus.queued).limit(1))
        ).first()
        if queued_job is None:
            return False

        active_hpc_workers = (
            await self._session.exec(
                select(Worker).where(
                    Worker.platform == Platform.hpc,
                    col(Worker.slurm_job_id).is_(None),
                    col(Worker.last_heartbeat) >= self._stale_cutoff,
                )
            )
        ).all()
        if active_hpc_workers:
            return False

        pending_prefix = f"{cluster.name}:"
        pending_workers = (
            await self._session.exec(
                select(Worker).where(
                    Worker.platform == Platform.hpc,
                    col(Worker.slurm_job_id).is_not(None),
                    col(Worker.slurm_job_id).startswith(pending_prefix),
                )
            )
        ).all()
        if len(pending_workers) >= cluster.max_pending_jobs:
            return False

        if not self._settings.infisical_token:
            return False

        slurm_job_id = await self._submit_job(
            cluster,
            self._settings,
        )
        placeholder_worker = Worker(
            id=uuid4(),
            platform=Platform.hpc,
            gpu_model=cluster.gpu_type,
            gpu_count=cluster.gpu_count,
            vram_gb=0,
            slurm_job_id=pending_slurm_job_marker(cluster.name, slurm_job_id),
            last_heartbeat=datetime(1970, 1, 1),
            registered_at=datetime(1970, 1, 1),
        )
        self._session.add(placeholder_worker)
        await self._session.commit()
        return True


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
