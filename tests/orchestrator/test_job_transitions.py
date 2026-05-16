from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from relaymd.models import Job, JobStatus

from relaymd.orchestrator.services import JobTransitionConflictError, JobTransitionService


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (JobStatus.queued, JobStatus.assigned),
        (JobStatus.queued, JobStatus.cancelled),
        (JobStatus.assigned, JobStatus.running),
        (JobStatus.assigned, JobStatus.completed),
        (JobStatus.assigned, JobStatus.failed),
        (JobStatus.assigned, JobStatus.cancelled),
        (JobStatus.assigned, JobStatus.queued),
        (JobStatus.running, JobStatus.completed),
        (JobStatus.running, JobStatus.failed),
        (JobStatus.running, JobStatus.cancelled),
        (JobStatus.running, JobStatus.queued),
        (JobStatus.running, JobStatus.handoff),
        (JobStatus.handoff, JobStatus.queued),
        (JobStatus.handoff, JobStatus.cancelled),
    ],
)
def test_transition_matrix_allows_expected_edges(start: JobStatus, target: JobStatus) -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=start)

    service.ensure_transition(job, target)


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (JobStatus.queued, JobStatus.running),
        (JobStatus.queued, JobStatus.completed),
        (JobStatus.queued, JobStatus.failed),
        (JobStatus.completed, JobStatus.queued),
        (JobStatus.failed, JobStatus.queued),
        (JobStatus.cancelled, JobStatus.queued),
        (JobStatus.completed, JobStatus.cancelled),
        (JobStatus.failed, JobStatus.completed),
    ],
)
def test_transition_matrix_rejects_invalid_edges(start: JobStatus, target: JobStatus) -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=start)

    with pytest.raises(JobTransitionConflictError):
        service.ensure_transition(job, target)


@pytest.mark.parametrize("status", [JobStatus.assigned, JobStatus.running, JobStatus.handoff])
def test_checkpoint_allowed_in_active_states(status: JobStatus) -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=status)
    status_changed_at = job.status_changed_at

    service.report_checkpoint(job, checkpoint_path="jobs/1/checkpoints/latest")

    assert job.latest_checkpoint_manifest_path == "jobs/1/checkpoints/latest"
    assert isinstance(job.last_checkpoint_at, datetime)
    assert job.status_changed_at == status_changed_at


def test_assignment_and_running_transitions_set_lifecycle_timestamps() -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz")
    worker_id = job.id

    service.assign_job(job, worker_id=worker_id)

    assert job.status == JobStatus.assigned
    assert job.assigned_worker_id == worker_id
    assert job.assigned_at == job.status_changed_at

    assigned_status_changed_at = job.status_changed_at
    service.mark_job_running(job)

    assert job.status == JobStatus.running
    assert job.started_at == job.status_changed_at
    assert job.status_changed_at >= assigned_status_changed_at


def test_mark_running_is_idempotent_without_resetting_timestamps() -> None:
    service = JobTransitionService()
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    job = Job(
        title="job",
        input_bundle_path="jobs/1/input/bundle.tar.gz",
        status=JobStatus.running,
        started_at=started_at,
        status_changed_at=started_at,
    )

    service.mark_job_running(job)

    assert job.started_at == started_at
    assert job.status_changed_at == started_at


def test_checkpoint_allowed_in_active_states_logs_checkpoint_recorded() -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=JobStatus.running)

    with patch("relaymd.orchestrator.services.job_transitions.logger.info") as info_mock:
        service.report_checkpoint(job, checkpoint_path="jobs/1/checkpoints/latest")

    info_mock.assert_called_once()
    assert info_mock.call_args.args[0] == "checkpoint_recorded"


def test_checkpoint_omitted_progress_fields_do_not_clear_existing_values() -> None:
    service = JobTransitionService()
    job = Job(
        title="job",
        input_bundle_path="jobs/1/input/bundle.tar.gz",
        status=JobStatus.running,
        progress=0.55,
        progress_codes_json='["progress_missing"]',
    )

    service.report_checkpoint(job, checkpoint_path="jobs/1/checkpoints/latest")

    assert job.progress == 0.55
    assert job.progress_codes_json == '["progress_missing"]'


@pytest.mark.parametrize(
    "status",
    [JobStatus.queued, JobStatus.completed, JobStatus.failed, JobStatus.cancelled],
)
def test_checkpoint_rejected_outside_active_states(status: JobStatus) -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=status)

    with pytest.raises(JobTransitionConflictError):
        service.report_checkpoint(job, checkpoint_path="jobs/1/checkpoints/latest")


def test_requeue_clone_requires_terminal_status() -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=JobStatus.running)

    with pytest.raises(JobTransitionConflictError):
        service.build_requeue_clone(job)


def test_requeue_clone_preserves_checkpoint_metadata() -> None:
    service = JobTransitionService()
    job = Job(
        title="job",
        input_bundle_path="jobs/1/input/bundle.tar.gz",
        status=JobStatus.failed,
        latest_checkpoint_manifest_path="jobs/1/checkpoints/latest",
        last_checkpoint_at=datetime.now(),
    )

    clone = service.build_requeue_clone(job)

    assert clone.id != job.id
    assert clone.status == JobStatus.queued
    assert clone.latest_checkpoint_manifest_path == job.latest_checkpoint_manifest_path
    assert clone.last_checkpoint_at == job.last_checkpoint_at
    assert clone.assigned_worker_id is None


def test_complete_handoff_requeues_without_clearing_existing_checkpoint() -> None:
    service = JobTransitionService()
    job = Job(
        title="job",
        input_bundle_path="jobs/1/input/bundle.tar.gz",
        status=JobStatus.handoff,
        latest_checkpoint_manifest_path="jobs/1/checkpoints/existing",
    )

    service.complete_handoff(job, checkpoint_cycle_status="partial")

    assert job.status == JobStatus.queued
    assert job.assigned_worker_id is None
    assert job.latest_checkpoint_manifest_path == "jobs/1/checkpoints/existing"
    assert job.checkpoint_cycle_status == "partial"
