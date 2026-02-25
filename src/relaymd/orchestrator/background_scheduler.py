from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.scheduler import (
    orphaned_job_requeue_once,
    sbatch_submission_job,
    stale_worker_reaper_job,
)


def build_background_scheduler(settings: OrchestratorSettings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        stale_worker_reaper_job,
        trigger="interval",
        seconds=settings.stale_worker_reaper_interval_seconds,
        args=[settings],
        id="stale_worker_reaper",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        orphaned_job_requeue_once,
        trigger="interval",
        seconds=settings.orphaned_job_requeue_interval_seconds,
        id="orphaned_job_requeue",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        sbatch_submission_job,
        trigger="interval",
        seconds=settings.sbatch_submission_interval_seconds,
        args=[settings],
        id="sbatch_submission",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
