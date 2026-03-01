from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, Worker
from relaymd.orchestrator import scheduling
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.logging import get_logger
from relaymd.orchestrator.services import WorkerLifecycleService
from relaymd.orchestrator.services.salad_autoscaling_service import SaladAutoscalingService
from relaymd.orchestrator.services.slurm_provisioning_service import (
    reap_dead_slurm_placeholders as _reap_dead_slurm_placeholders,
)
from relaymd.orchestrator.services.slurm_provisioning_service import (
    submit_pending_slurm_jobs as _submit_pending_slurm_jobs,
)
from relaymd.orchestrator.slurm import submit_slurm_job

LOG = get_logger(__name__)


async def assign_job(
    session: AsyncSession,
    settings: OrchestratorSettings,
) -> tuple[Job, Worker] | None:
    return await scheduling.assign_job(
        session,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        heartbeat_timeout_multiplier=settings.heartbeat_timeout_multiplier,
    )


async def reap_stale_workers(settings: OrchestratorSettings) -> int:
    sessionmaker = get_sessionmaker()
    timeout_seconds = settings.heartbeat_timeout_multiplier * settings.heartbeat_interval_seconds
    stale_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

    async with sessionmaker() as session:
        service = WorkerLifecycleService(session)
        return await service.reap_stale_workers(stale_cutoff=stale_cutoff)


async def stale_worker_reaper_job(settings: OrchestratorSettings) -> None:
    await reap_stale_workers(settings)
    try:
        await apply_salad_autoscaling_policy(settings)
    except Exception:  # noqa: BLE001
        LOG.warning("salad_autoscaling_failed", exc_info=True)


async def apply_salad_autoscaling_policy(settings: OrchestratorSettings) -> None:
    await SaladAutoscalingService(settings).apply()


async def orphaned_job_requeue_once() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        service = WorkerLifecycleService(session)
        await service.requeue_orphaned_jobs_once()


async def submit_pending_slurm_jobs(settings: OrchestratorSettings) -> int:
    return await _submit_pending_slurm_jobs(settings, submit_job=submit_slurm_job)


async def reap_dead_slurm_placeholders(settings: OrchestratorSettings) -> int:
    return await _reap_dead_slurm_placeholders(settings)


async def sbatch_submission_job(settings: OrchestratorSettings) -> None:
    try:
        await reap_dead_slurm_placeholders(settings)
    except Exception:  # noqa: BLE001
        LOG.warning("dead_slurm_placeholder_reap_failed", exc_info=True)
    await submit_pending_slurm_jobs(settings)
