from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import col, select

from relaymd.models import Job, JobStatus, Platform, Worker
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_sessionmaker
from relaymd.orchestrator.salad_scaler import SaladScaler


class SaladAutoscalingService:
    def __init__(self, settings: OrchestratorSettings) -> None:
        self._settings = settings

    async def apply(self) -> None:
        settings = self._settings
        if (
            settings.salad_api_key is None
            or settings.salad_org is None
            or settings.salad_project is None
            or settings.salad_container_group is None
        ):
            return

        timeout_seconds = (
            settings.heartbeat_timeout_multiplier * settings.heartbeat_interval_seconds
        )
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
            busy_worker_id_set = {
                worker_id for worker_id in busy_worker_ids if worker_id is not None
            }
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
            timeout_seconds=settings.salad_api_timeout_seconds,
        )
        current_replicas = await scaler.get_current_replicas()
        if current_replicas != scale_target:
            await scaler.scale(scale_target)
