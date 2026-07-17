from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import Job, JobStatus, Worker, WorkerRegister, WorkerStatus
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.services.slurm_provisioning_service import (
    _query_live_slurm_job_statuses,
)
from relaymd.storage import StorageClient

from .job_history_service import append_job_event
from .job_transitions import JobTransitionService

logger = structlog.get_logger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WorkerLifecycleService:
    def __init__(
        self, session: AsyncSession, *, settings: OrchestratorSettings | None = None
    ) -> None:
        self._session = session
        self._transitions = JobTransitionService()
        self._settings = settings

    def _build_storage_client(self) -> StorageClient | None:
        if self._settings is None:
            return None
        if self._settings.storage_provider == "purdue":
            if not (
                self._settings.purdue_s3_endpoint
                and self._settings.purdue_s3_bucket_name
                and self._settings.purdue_s3_access_key
                and self._settings.purdue_s3_secret_key
            ):
                return None
            return StorageClient(
                storage_provider="purdue",
                b2_endpoint_url=self._settings.purdue_s3_endpoint,
                b2_bucket_name=self._settings.purdue_s3_bucket_name,
                b2_access_key_id=self._settings.purdue_s3_access_key,
                b2_secret_access_key=self._settings.purdue_s3_secret_key,
                cf_worker_url=self._settings.cf_worker_url,
                cf_bearer_token="",
                s3_region_name="us-east-1",
            )

        if not (
            self._settings.b2_endpoint_url
            and self._settings.b2_bucket_name
            and self._settings.b2_access_key_id
            and self._settings.b2_secret_access_key
        ):
            return None
        return StorageClient(
            storage_provider="cloudflare_backblaze",
            b2_endpoint_url=self._settings.b2_endpoint_url,
            b2_bucket_name=self._settings.b2_bucket_name,
            b2_access_key_id=self._settings.b2_access_key_id,
            b2_secret_access_key=self._settings.b2_secret_access_key,
            cf_worker_url=self._settings.cf_worker_url,
            cf_bearer_token=self._settings.cf_bearer_token,
            s3_region_name=None,
        )

    async def _status_is_fresh(self, *, storage: StorageClient | None, job_id: UUID) -> bool:
        if storage is None or self._settings is None:
            return False
        key = f"jobs/{job_id}/checkpoints/status.json"
        with tempfile.TemporaryDirectory(prefix=f"relaymd-status-{job_id}-") as tmpdir:
            path = Path(tmpdir) / "status.json"
            try:
                storage.download_file(key, path)
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return False
        if not isinstance(payload, dict):
            return False
        updated_at_raw = payload.get("updated_at")
        if not isinstance(updated_at_raw, str) or not updated_at_raw:
            return False
        try:
            updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00")).astimezone(
                UTC
            )
        except ValueError:
            return False

        interval_raw = payload.get("checkpoint_poll_interval_seconds")
        interval_seconds = (
            int(interval_raw)
            if isinstance(interval_raw, int) and interval_raw > 0
            else self._settings.worker_checkpoint_poll_interval_seconds
        )
        stale_threshold_seconds = interval_seconds * 6
        age_seconds = (datetime.now(UTC) - updated_at).total_seconds()
        return age_seconds <= stale_threshold_seconds

    async def register_worker(self, payload: WorkerRegister) -> Worker:
        """Register a worker, activating an existing queued placeholder if one matches.

        When a SLURM-launched worker starts, it passes ``provider_id`` (composed
        from ``RELAYMD_CLUSTER_NAME`` + ``SLURM_JOB_ID`` in the sbatch environment).
        If a queued placeholder with that exact ``provider_id`` exists, we activate
        it in-place — updating the real VRAM, heartbeat, and status — so the same
        UUID represents the worker across its entire lifecycle, from submission to
        completion. This avoids orphaned placeholder rows without requiring a
        sentinel-based string encoding.

        If no matching placeholder is found (Salad workers, or a SLURM worker whose
        placeholder was already reaped), a fresh row is inserted.
        """
        if payload.provider_id:
            existing = (
                await self._session.exec(
                    select(Worker).where(
                        Worker.provider_id == payload.provider_id,
                        Worker.status == WorkerStatus.queued,
                        Worker.worker_image_key == payload.worker_image_key,
                    )
                )
            ).first()
            if existing is not None:
                logger.info(
                    "queued_placeholder_activated",
                    provider_id=payload.provider_id,
                    worker_id=str(existing.id),
                    platform=str(payload.platform),
                )
                existing.status = WorkerStatus.active
                existing.vram_gb = payload.vram_gb
                existing.gpu_model = payload.gpu_model
                existing.gpu_count = payload.gpu_count
                existing.last_heartbeat = _utcnow_naive()
                existing.provider_state = None
                existing.provider_state_raw = None
                existing.provider_reason = None
                existing.provider_last_checked_at = None
                self._session.add(existing)
                await self._session.commit()
                await self._session.refresh(existing)
                return existing

        worker = Worker(
            platform=payload.platform,
            gpu_model=payload.gpu_model,
            gpu_count=payload.gpu_count,
            vram_gb=payload.vram_gb,
            worker_image_key=payload.worker_image_key,
            provider_id=payload.provider_id,
            status=WorkerStatus.active,
        )
        self._session.add(worker)
        await self._session.commit()
        await self._session.refresh(worker)
        logger.info(
            "worker_registered",
            worker_id=str(worker.id),
            provider_id=worker.provider_id,
            platform=str(worker.platform),
            worker_image_key=worker.worker_image_key,
        )
        return worker

    async def heartbeat(
        self,
        worker_id: UUID,
        *,
        job_id: UUID | None = None,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
    ) -> Worker | None:
        worker = await self._session.get(Worker, worker_id)
        if worker is None:
            return None

        worker.last_heartbeat = _utcnow_naive()
        self._session.add(worker)
        if job_id is not None:
            job = (
                await self._session.exec(
                    select(Job).where(Job.id == job_id, Job.assigned_worker_id == worker_id)
                )
            ).first()
            if job is not None:
                if progress is not None:
                    job.progress = progress
                if progress_codes is not None:
                    job.progress_codes_json = json.dumps(progress_codes)
                job.updated_at = _utcnow_naive()
                self._session.add(job)
        await self._session.commit()
        return worker

    async def deregister(self, worker_id: UUID) -> bool:
        worker = await self._session.get(Worker, worker_id)
        if worker is None:
            return False

        jobs = (
            await self._session.exec(
                select(Job).where(
                    Job.assigned_worker_id == worker_id,
                    col(Job.status).in_(
                        [JobStatus.assigned, JobStatus.running, JobStatus.cancelling]
                    ),
                )
            )
        ).all()
        for job in jobs:
            previous_status = job.status
            previous_worker_id = job.assigned_worker_id
            if job.status == JobStatus.cancelling:
                self._transitions.cancel_job(job)
                event_type = "cancelled"
                status_to = JobStatus.cancelled
            else:
                self._transitions.requeue_in_place(job)
                event_type = "worker_deregistered_requeue"
                status_to = JobStatus.queued
            self._session.add(job)
            await append_job_event(
                self._session,
                job_id=job.id,
                event_type=event_type,
                worker_id=previous_worker_id,
                status_from=previous_status,
                status_to=status_to,
            )

        await self._session.delete(worker)
        await self._session.commit()
        return True

    async def reap_stale_workers(self, *, stale_cutoff: datetime) -> int:
        storage = self._build_storage_client()
        stale_workers = (
            await self._session.exec(
                select(Worker).where(
                    col(Worker.last_heartbeat) < stale_cutoff,
                    # Only reap active workers — queued placeholders are managed
                    # by reap_dead_slurm_placeholders via squeue.
                    Worker.status == WorkerStatus.active,
                )
            )
        ).all()
        if not stale_workers:
            await self._session.commit()
            return 0

        stale_worker_ids = [worker.id for worker in stale_workers]
        jobs_by_worker: dict[UUID, list[Job]] = {}
        jobs_to_evaluate = (
            await self._session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).in_(stale_worker_ids),
                    col(Job.status).in_(
                        [JobStatus.assigned, JobStatus.running, JobStatus.cancelling]
                    ),
                )
            )
        ).all()
        for job in jobs_to_evaluate:
            if job.assigned_worker_id is None:
                continue
            jobs_by_worker.setdefault(job.assigned_worker_id, []).append(job)

        now = _utcnow_naive()
        slurm_clusters = {
            cluster.name: cluster
            for cluster in (self._settings.slurm_cluster_configs if self._settings else [])
        }
        provider_check_interval_seconds = 120
        if self._settings is not None:
            provider_check_interval_seconds = int(
                self._settings.heartbeat_interval_seconds
                * self._settings.heartbeat_timeout_multiplier
            )

        workers_to_delete: list[Worker] = []
        for worker in stale_workers:
            assigned_jobs = jobs_by_worker.get(worker.id, [])
            status_fresh = False
            if assigned_jobs:
                status_fresh = await self._status_is_fresh(
                    storage=storage,
                    job_id=assigned_jobs[0].id,
                )

            provider_alive = False
            if worker.platform.value == "hpc" and worker.provider_id and ":" in worker.provider_id:
                cluster_name, raw_job_id = worker.provider_id.split(":", 1)
                cluster = slurm_clusters.get(cluster_name)
                should_query = (
                    worker.provider_last_checked_at is None
                    or (now - worker.provider_last_checked_at).total_seconds()
                    >= provider_check_interval_seconds
                )
                if cluster is not None and should_query:
                    statuses = await _query_live_slurm_job_statuses(cluster, [raw_job_id])
                    if statuses is None:
                        # SLURM query can fail transiently; do not treat unknown as dead.
                        provider_alive = True
                    else:
                        status = statuses.get(raw_job_id)
                        if status is None:
                            worker.provider_state = "gone"
                            worker.provider_state_raw = "GONE"
                            worker.provider_reason = None
                        else:
                            worker.provider_state = status.provider_state
                            worker.provider_state_raw = status.provider_state_raw
                            worker.provider_reason = status.provider_reason
                            provider_alive = status.provider_state in {
                                "pending",
                                "running",
                                "completing",
                            }
                        worker.provider_last_checked_at = now
                        self._session.add(worker)
                elif worker.provider_state in {"pending", "running", "completing"}:
                    provider_alive = True

            if status_fresh or provider_alive:
                if not status_fresh and provider_alive and assigned_jobs:
                    logger.warning(
                        "stale_worker_progress_status_stale_provider_running",
                        worker_id=str(worker.id),
                        provider_id=worker.provider_id,
                        job_id=str(assigned_jobs[0].id),
                    )
                continue

            for job in assigned_jobs:
                previous_status = job.status
                previous_worker_id = job.assigned_worker_id
                if job.status == JobStatus.cancelling:
                    self._transitions.cancel_job(job)
                    event_type = "cancelled"
                    status_to = JobStatus.cancelled
                else:
                    self._transitions.requeue_in_place(job)
                    event_type = "worker_deregistered_requeue"
                    status_to = JobStatus.queued
                self._session.add(job)
                await append_job_event(
                    self._session,
                    job_id=job.id,
                    event_type=event_type,
                    worker_id=previous_worker_id,
                    status_from=previous_status,
                    status_to=status_to,
                )
            workers_to_delete.append(worker)

        for worker in workers_to_delete:
            await self._session.delete(worker)

        await self._session.commit()
        return len(workers_to_delete)

    async def _legacy_reap_stale_workers(self, *, stale_cutoff: datetime) -> int:
        stale_workers = (
            await self._session.exec(
                select(Worker).where(
                    col(Worker.last_heartbeat) < stale_cutoff,
                    Worker.status == WorkerStatus.active,
                )
            )
        ).all()
        stale_worker_ids = [worker.id for worker in stale_workers]
        jobs_to_requeue = (
            await self._session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).in_(stale_worker_ids),
                    col(Job.status).in_(
                        [JobStatus.assigned, JobStatus.running, JobStatus.cancelling]
                    ),
                )
            )
        ).all()
        for job in jobs_to_requeue:
            previous_status = job.status
            previous_worker_id = job.assigned_worker_id
            if job.status == JobStatus.cancelling:
                self._transitions.cancel_job(job)
                event_type = "cancelled"
                status_to = JobStatus.cancelled
            else:
                self._transitions.requeue_in_place(job)
                event_type = "worker_deregistered_requeue"
                status_to = JobStatus.queued
            self._session.add(job)
            await append_job_event(
                self._session,
                job_id=job.id,
                event_type=event_type,
                worker_id=previous_worker_id,
                status_from=previous_status,
                status_to=status_to,
            )

        for worker in stale_workers:
            await self._session.delete(worker)

        await self._session.commit()
        return len(stale_workers)

    async def requeue_orphaned_jobs_once(self) -> int:
        worker_ids = set((await self._session.exec(select(Worker.id))).all())
        assigned_jobs = (
            await self._session.exec(
                select(Job).where(
                    col(Job.assigned_worker_id).is_not(None),
                    col(Job.status).in_(
                        [JobStatus.assigned, JobStatus.running, JobStatus.cancelling]
                    ),
                )
            )
        ).all()

        requeued_count = 0
        for job in assigned_jobs:
            if job.assigned_worker_id not in worker_ids:
                previous_status = job.status
                previous_worker_id = job.assigned_worker_id
                if job.status == JobStatus.cancelling:
                    self._transitions.cancel_job(job)
                    event_type = "cancelled"
                    status_to = JobStatus.cancelled
                else:
                    self._transitions.requeue_in_place(job)
                    event_type = "worker_deregistered_requeue"
                    status_to = JobStatus.queued
                self._session.add(job)
                await append_job_event(
                    self._session,
                    job_id=job.id,
                    event_type=event_type,
                    worker_id=previous_worker_id,
                    status_from=previous_status,
                    status_to=status_to,
                )
                requeued_count += 1

        if requeued_count > 0:
            await self._session.commit()
            return requeued_count

        await self._session.rollback()
        return 0
