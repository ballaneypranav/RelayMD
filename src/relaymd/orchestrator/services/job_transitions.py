from __future__ import annotations

from uuid import UUID

import structlog

from relaymd.models import Job, JobStatus
from relaymd.models.job import utcnow_naive

from .errors import JobTransitionConflictError

logger = structlog.get_logger(__name__)

TERMINAL_JOB_STATUSES = {
    JobStatus.completed,
    JobStatus.failed,
    JobStatus.cancelled,
}

ACTIVE_CHECKPOINT_JOB_STATUSES = {
    JobStatus.assigned,
    JobStatus.running,
}

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.queued: {JobStatus.assigned, JobStatus.cancelled},
    JobStatus.assigned: {
        JobStatus.running,
        JobStatus.completed,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.queued,
    },
    JobStatus.running: {
        JobStatus.completed,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.queued,
    },
    JobStatus.completed: set(),
    JobStatus.failed: set(),
    JobStatus.cancelled: set(),
}


class JobTransitionService:
    """State authority for all in-place job status mutations."""

    def ensure_transition(self, job: Job, target_status: JobStatus) -> None:
        allowed = ALLOWED_TRANSITIONS.get(job.status, set())
        if target_status in allowed:
            return

        raise JobTransitionConflictError(
            message=f"Transition {job.status.value} -> {target_status.value} is not allowed",
            job_id=job.id,
            current_status=job.status,
            requested_status=target_status,
        )

    def _transition(
        self,
        job: Job,
        target_status: JobStatus,
        *,
        clear_assigned_worker: bool = False,
        assigned_worker_id: UUID | None = None,
    ) -> Job:
        self.ensure_transition(job, target_status)
        job.status = target_status
        if clear_assigned_worker:
            job.assigned_worker_id = None
        elif assigned_worker_id is not None:
            job.assigned_worker_id = assigned_worker_id
        job.updated_at = utcnow_naive()
        return job

    def assign_job(self, job: Job, *, worker_id: UUID) -> Job:
        return self._transition(job, JobStatus.assigned, assigned_worker_id=worker_id)

    def mark_job_running(self, job: Job) -> Job:
        return self._transition(job, JobStatus.running)

    def mark_job_completed(self, job: Job) -> Job:
        updated_job = self._transition(job, JobStatus.completed)
        logger.info(
            "job_completed_reported", job_id=str(job.id), worker_id=str(job.assigned_worker_id)
        )
        return updated_job

    def mark_job_failed(self, job: Job) -> Job:
        updated_job = self._transition(job, JobStatus.failed)
        logger.info(
            "job_failed_reported", job_id=str(job.id), worker_id=str(job.assigned_worker_id)
        )
        return updated_job

    def cancel_job(self, job: Job) -> Job:
        worker_id = str(job.assigned_worker_id) if job.assigned_worker_id is not None else None
        updated_job = self._transition(job, JobStatus.cancelled, clear_assigned_worker=True)
        logger.info("job_cancelled", job_id=str(job.id), worker_id=worker_id)
        return updated_job

    def requeue_in_place(self, job: Job) -> Job:
        return self._transition(job, JobStatus.queued, clear_assigned_worker=True)

    def report_checkpoint(self, job: Job, *, checkpoint_path: str) -> Job:
        if job.status not in ACTIVE_CHECKPOINT_JOB_STATUSES:
            raise JobTransitionConflictError(
                message=(
                    "Checkpoint updates are allowed only for jobs in assigned or running state"
                ),
                job_id=job.id,
                current_status=job.status,
                requested_status=None,
            )

        now = utcnow_naive()
        job.latest_checkpoint_path = checkpoint_path
        job.last_checkpoint_at = now
        job.updated_at = now
        logger.info(
            "checkpoint_recorded",
            job_id=str(job.id),
            worker_id=str(job.assigned_worker_id) if job.assigned_worker_id is not None else None,
            latest_checkpoint_path=checkpoint_path,
            last_checkpoint_at=now.isoformat(),
        )
        return job

    def build_requeue_clone(self, job: Job) -> Job:
        if job.status not in TERMINAL_JOB_STATUSES:
            raise JobTransitionConflictError(
                message=(
                    "Requeue clone is allowed only for terminal jobs (completed, failed, cancelled)"
                ),
                job_id=job.id,
                current_status=job.status,
                requested_status=JobStatus.queued,
            )

        now = utcnow_naive()
        return Job(
            title=job.title,
            input_bundle_path=job.input_bundle_path,
            status=JobStatus.queued,
            latest_checkpoint_path=job.latest_checkpoint_path,
            last_checkpoint_at=job.last_checkpoint_at,
            assigned_worker_id=None,
            created_at=now,
            updated_at=now,
        )
