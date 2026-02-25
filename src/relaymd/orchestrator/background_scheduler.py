from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.scheduler import (
    HEARTBEAT_INTERVAL_SECONDS,
    SBATCH_INTERVAL_SECONDS,
    orphaned_job_requeue_once,
    sbatch_submission_job,
    stale_worker_reaper_job,
)


def build_background_scheduler(settings: OrchestratorSettings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        stale_worker_reaper_job,
        trigger="interval",
        seconds=HEARTBEAT_INTERVAL_SECONDS,
        args=[settings],
        id="stale_worker_reaper",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        orphaned_job_requeue_once,
        trigger="interval",
        seconds=HEARTBEAT_INTERVAL_SECONDS,
        id="orphaned_job_requeue",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        sbatch_submission_job,
        trigger="interval",
        seconds=SBATCH_INTERVAL_SECONDS,
        args=[settings],
        id="sbatch_submission",
        coalesce=True,
        max_instances=1,
    )
    return scheduler
