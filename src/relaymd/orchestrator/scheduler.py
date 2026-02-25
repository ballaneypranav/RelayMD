from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Select
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Platform, Worker
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.salad_scaler import SaladScaler
from relaymd.orchestrator.scheduling import score_worker
from relaymd.orchestrator.slurm import submit_slurm_job

HEARTBEAT_INTERVAL_SECONDS = 30
SBATCH_INTERVAL_SECONDS = 60


async def assign_job(session: AsyncSession) -> tuple[Job, Worker] | None:
    queued_job_statement: Select[tuple[Job]] = (
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(col(Job.created_at).asc())
        .limit(1)
    )
    queued_job = (await session.exec(queued_job_statement)).first()
    if queued_job is None:
        return None

    busy_worker_ids = (
        await session.exec(
            select(Job.assigned_worker_id).where(
                col(Job.assigned_worker_id).is_not(None),
                col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
            )
        )
    ).all()
    busy_worker_id_set = {worker_id for worker_id in busy_worker_ids if worker_id is not None}

    all_workers = (await session.exec(select(Worker))).all()
    idle_workers = [worker for worker in all_workers if worker.id not in busy_worker_id_set]
    if not idle_workers:
        return None

    selected_worker = max(
        idle_workers,
        key=lambda worker: (score_worker(worker), worker.registered_at.timestamp() * -1),
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    queued_job.assigned_worker_id = selected_worker.id
    queued_job.status = JobStatus.assigned
    queued_job.updated_at = now

    session.add(queued_job)
    await session.commit()
    await session.refresh(queued_job)

    return queued_job, selected_worker


async def reap_stale_workers(settings: OrchestratorSettings) -> int:
    sessionmaker = get_sessionmaker()
    timeout_seconds = settings.heartbeat_timeout_multiplier * HEARTBEAT_INTERVAL_SECONDS
    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

    async with sessionmaker() as session:
        stale_workers = (
            await session.exec(select(Worker).where(col(Worker.last_heartbeat) < stale_cutoff))
        ).all()
        if not stale_workers:
            await session.commit()
            return 0

        stale_worker_ids = [worker.id for worker in stale_workers]
        jobs_to_requeue = (
            await session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).in_(stale_worker_ids),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()

        now = datetime.now(UTC).replace(tzinfo=None)
        for job in jobs_to_requeue:
            job.status = JobStatus.queued
            job.assigned_worker_id = None
            job.updated_at = now
            session.add(job)

        for worker in stale_workers:
            await session.delete(worker)

        await session.commit()
        return len(stale_workers)


async def stale_worker_reaper_job(settings: OrchestratorSettings) -> None:
    await reap_stale_workers(settings)
    await apply_salad_autoscaling_policy(settings)


async def apply_salad_autoscaling_policy(settings: OrchestratorSettings) -> None:
    if (
        settings.salad_api_key is None
        or settings.salad_org is None
        or settings.salad_project is None
        or settings.salad_container_group is None
    ):
        return

    timeout_seconds = settings.heartbeat_timeout_multiplier * HEARTBEAT_INTERVAL_SECONDS
    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        queued_job_ids = (
            await session.exec(select(Job.id).where(Job.status == JobStatus.queued))
        ).all()
        queued_jobs_count = len(queued_job_ids)
        busy_worker_ids = (
            await session.exec(
                select(Job.assigned_worker_id).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()
        busy_worker_id_set = {worker_id for worker_id in busy_worker_ids if worker_id is not None}
        fresh_hpc_workers = (
            await session.exec(
                select(Worker).where(
                    Worker.platform == Platform.hpc,
                    col(Worker.last_heartbeat) >= stale_cutoff,
                )
            )
        ).all()
        idle_hpc_workers = [
            worker for worker in fresh_hpc_workers if worker.id not in busy_worker_id_set
        ]

    scale_target: int | None = None
    if queued_jobs_count > 0 and len(idle_hpc_workers) == 0:
        scale_target = min(queued_jobs_count, settings.salad_max_replicas)
    elif queued_jobs_count == 0:
        scale_target = 0

    if scale_target is None:
        return

    scaler = SaladScaler(
        organization_name=settings.salad_org,
        project_name=settings.salad_project,
        container_group_name=settings.salad_container_group,
        api_key=settings.salad_api_key,
        max_replicas=settings.salad_max_replicas,
    )
    current_replicas = await scaler.get_current_replicas()
    if current_replicas != scale_target:
        await scaler.scale(scale_target)


async def orphaned_job_requeue_once() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        worker_ids = set((await session.exec(select(Worker.id))).all())
        assigned_jobs = (
            await session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_([JobStatus.assigned, JobStatus.running]),
                )
            )
        ).all()

        now = datetime.now(UTC).replace(tzinfo=None)
        changed = False
        for job in assigned_jobs:
            if job.assigned_worker_id not in worker_ids:
                job.status = JobStatus.queued
                job.assigned_worker_id = None
                job.updated_at = now
                session.add(job)
                changed = True

        if changed:
            await session.commit()
        else:
            await session.rollback()


def _pending_slurm_job_marker(cluster_name: str, slurm_job_id: str) -> str:
    return f"{cluster_name}:{slurm_job_id}"


async def _submit_cluster_if_needed(
    session: AsyncSession,
    *,
    settings: OrchestratorSettings,
    cluster: ClusterConfig,
    stale_cutoff: datetime,
) -> bool:
    queued_job = (
        await session.exec(select(Job).where(Job.status == JobStatus.queued).limit(1))
    ).first()
    if queued_job is None:
        return False

    active_hpc_workers = (
        await session.exec(
            select(Worker).where(
                Worker.platform == Platform.hpc,
                col(Worker.slurm_job_id).is_(None),
                col(Worker.last_heartbeat) >= stale_cutoff,
            )
        )
    ).all()
    if active_hpc_workers:
        return False

    pending_prefix = f"{cluster.name}:"
    pending_workers = (
        await session.exec(
            select(Worker).where(
                Worker.platform == Platform.hpc,
                col(Worker.slurm_job_id).is_not(None),
                col(Worker.slurm_job_id).startswith(pending_prefix),
            )
        )
    ).all()
    if len(pending_workers) >= cluster.max_pending_jobs:
        return False

    if not settings.infisical_token:
        return False

    slurm_job_id = await submit_slurm_job(
        cluster=cluster,
        gpu_count=cluster.gpu_count,
        infisical_token=settings.infisical_token,
    )
    placeholder_worker = Worker(
        id=uuid4(),
        platform=Platform.hpc,
        gpu_model=cluster.gpu_type,
        gpu_count=cluster.gpu_count,
        vram_gb=0,
        slurm_job_id=_pending_slurm_job_marker(cluster.name, slurm_job_id),
        last_heartbeat=datetime(1970, 1, 1),
        registered_at=datetime(1970, 1, 1),
    )
    session.add(placeholder_worker)
    await session.commit()
    return True


async def submit_pending_slurm_jobs(settings: OrchestratorSettings) -> int:
    if not settings.slurm_cluster_configs:
        return 0

    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        seconds=settings.heartbeat_timeout_multiplier * HEARTBEAT_INTERVAL_SECONDS
    )
    sessionmaker = get_sessionmaker()
    submissions = 0
    async with sessionmaker() as session:
        for cluster in settings.slurm_cluster_configs:
            submitted = await _submit_cluster_if_needed(
                session,
                settings=settings,
                cluster=cluster,
                stale_cutoff=stale_cutoff,
            )
            if submitted:
                submissions += 1
    return submissions


async def sbatch_submission_job(settings: OrchestratorSettings) -> None:
    await submit_pending_slurm_jobs(settings)
