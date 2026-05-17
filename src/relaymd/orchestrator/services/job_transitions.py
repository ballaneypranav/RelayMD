from __future__ import annotations

import json
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
    JobStatus.cancelling,
    JobStatus.handoff,
}

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.queued: {JobStatus.assigned, JobStatus.cancelled},
    JobStatus.assigned: {
        JobStatus.running,
        JobStatus.completed,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.cancelling,
        JobStatus.queued,
    },
    JobStatus.running: {
        JobStatus.handoff,
        JobStatus.completed,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.cancelling,
        JobStatus.queued,
    },
    JobStatus.handoff: {
        JobStatus.queued,
        JobStatus.cancelled,
        JobStatus.cancelling,
    },
    JobStatus.cancelling: {JobStatus.cancelled},
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
        if target_status != JobStatus.queued:
            job.queue_blocked_reason = None
        now = utcnow_naive()
        job.status_changed_at = now
        job.updated_at = now
        return job

    def assign_job(self, job: Job, *, worker_id: UUID) -> Job:
        updated_job = self._transition(job, JobStatus.assigned, assigned_worker_id=worker_id)
        updated_job.assigned_at = updated_job.status_changed_at
        return updated_job

    def mark_job_running(self, job: Job) -> Job:
        if job.status == JobStatus.running:
            return job

        updated_job = self._transition(job, JobStatus.running)
        updated_job.started_at = updated_job.status_changed_at
        return updated_job

    def mark_job_completed(self, job: Job) -> Job:
        updated_job = self._transition(job, JobStatus.completed)
        logger.info(
            "job_completed_reported", job_id=str(job.id), worker_id=str(job.assigned_worker_id)
        )
        return updated_job

    def mark_job_failed(
        self,
        job: Job,
        *,
        failure_artifact_path: str | None = None,
    ) -> Job:
        updated_job = self._transition(job, JobStatus.failed)
        if failure_artifact_path is not None:
            updated_job.latest_failure_artifact_path = failure_artifact_path
        logger.info(
            "job_failed_reported", job_id=str(job.id), worker_id=str(job.assigned_worker_id)
        )
        return updated_job

    def request_job_cancellation(self, job: Job) -> Job:
        updated_job = self._transition(job, JobStatus.cancelling)
        updated_job.cancellation_requested_at = updated_job.status_changed_at
        logger.info(
            "job_cancellation_requested",
            job_id=str(job.id),
            worker_id=str(job.assigned_worker_id) if job.assigned_worker_id is not None else None,
        )
        return updated_job

    def cancel_job(self, job: Job) -> Job:
        worker_id = str(job.assigned_worker_id) if job.assigned_worker_id is not None else None
        updated_job = self._transition(job, JobStatus.cancelled, clear_assigned_worker=True)
        logger.info("job_cancelled", job_id=str(job.id), worker_id=worker_id)
        return updated_job

    def requeue_in_place(self, job: Job) -> Job:
        return self._transition(job, JobStatus.queued, clear_assigned_worker=True)

    def start_handoff(self, job: Job) -> Job:
        return self._transition(job, JobStatus.handoff)

    def complete_handoff(
        self,
        job: Job,
        *,
        checkpoint_manifest_path: str | None = None,
        checkpoint_path: str | None = None,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
        checkpoint_cycle_status: str | None = None,
        checkpoint_cycle_failures: list[dict[str, str]] | None = None,
    ) -> Job:
        if checkpoint_manifest_path is not None or checkpoint_path is not None:
            self.report_checkpoint(
                job,
                checkpoint_manifest_path=checkpoint_manifest_path,
                checkpoint_path=checkpoint_path,
                progress=progress,
                progress_codes=progress_codes,
                checkpoint_cycle_status=checkpoint_cycle_status,
                checkpoint_cycle_failures=checkpoint_cycle_failures,
            )
        else:
            now = utcnow_naive()
            if progress is not None:
                job.progress = progress
            if progress_codes is not None:
                job.progress_codes_json = json.dumps(progress_codes)
            if checkpoint_cycle_status is not None:
                job.checkpoint_cycle_status = checkpoint_cycle_status
            if checkpoint_cycle_failures is not None:
                job.checkpoint_cycle_failures_json = json.dumps(checkpoint_cycle_failures)
            job.updated_at = now
        return self.requeue_in_place(job)

    def report_checkpoint(
        self,
        job: Job,
        *,
        checkpoint_manifest_path: str | None = None,
        checkpoint_path: str | None = None,
        progress: float | None = None,
        progress_codes: list[str] | None = None,
        checkpoint_cycle_status: str | None = None,
        checkpoint_cycle_failures: list[dict[str, str]] | None = None,
    ) -> Job:
        resolved_checkpoint_manifest_path = checkpoint_manifest_path or checkpoint_path
        if resolved_checkpoint_manifest_path is None:
            raise JobTransitionConflictError(
                message="Checkpoint path is required",
                job_id=job.id,
                current_status=job.status,
                requested_status=None,
            )
        if job.status not in ACTIVE_CHECKPOINT_JOB_STATUSES:
            raise JobTransitionConflictError(
                message=(
                    "Checkpoint updates are allowed only for jobs in assigned, running, "
                    "cancelling, or handoff state"
                ),
                job_id=job.id,
                current_status=job.status,
                requested_status=None,
            )

        now = utcnow_naive()
        job.latest_checkpoint_manifest_path = resolved_checkpoint_manifest_path
        job.last_checkpoint_at = now
        if progress is not None:
            job.progress = progress
        if progress_codes is not None:
            job.progress_codes_json = json.dumps(progress_codes)
        if checkpoint_cycle_status is not None:
            job.checkpoint_cycle_status = checkpoint_cycle_status
        if checkpoint_cycle_failures is not None:
            job.checkpoint_cycle_failures_json = json.dumps(checkpoint_cycle_failures)
        job.updated_at = now
        logger.info(
            "checkpoint_recorded",
            job_id=str(job.id),
            worker_id=str(job.assigned_worker_id) if job.assigned_worker_id is not None else None,
            latest_checkpoint_manifest_path=resolved_checkpoint_manifest_path,
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
            preferred_clusters_json=job.preferred_clusters_json,
            comment=job.comment,
            queue_blocked_reason=None,
            status=JobStatus.queued,
            latest_checkpoint_manifest_path=job.latest_checkpoint_manifest_path,
            last_checkpoint_at=job.last_checkpoint_at,
            assigned_worker_id=None,
            created_at=now,
            status_changed_at=now,
            updated_at=now,
        )
