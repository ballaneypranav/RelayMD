from __future__ import annotations

from datetime import datetime

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


@pytest.mark.parametrize("status", [JobStatus.assigned, JobStatus.running])
def test_checkpoint_allowed_in_active_states(status: JobStatus) -> None:
    service = JobTransitionService()
    job = Job(title="job", input_bundle_path="jobs/1/input/bundle.tar.gz", status=status)

    service.report_checkpoint(job, checkpoint_path="jobs/1/checkpoints/latest")

    assert job.latest_checkpoint_path == "jobs/1/checkpoints/latest"
    assert isinstance(job.last_checkpoint_at, datetime)


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
        latest_checkpoint_path="jobs/1/checkpoints/latest",
        last_checkpoint_at=datetime.now(),
    )

    clone = service.build_requeue_clone(job)

    assert clone.id != job.id
    assert clone.status == JobStatus.queued
    assert clone.latest_checkpoint_path == job.latest_checkpoint_path
    assert clone.last_checkpoint_at == job.last_checkpoint_at
    assert clone.assigned_worker_id is None
