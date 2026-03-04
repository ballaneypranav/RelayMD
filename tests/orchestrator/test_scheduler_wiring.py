from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.orchestrator import background_scheduler, scheduler, scheduling
from relaymd.orchestrator.config import OrchestratorSettings


def _settings(**overrides: object) -> OrchestratorSettings:
    base: dict[str, object] = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "api_token": "test-token",
    }
    base.update(overrides)
    return OrchestratorSettings.model_validate(base)


class _SessionContextManager:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False


def test_build_background_scheduler_registers_expected_jobs(monkeypatch) -> None:
    class FakeScheduler:
        def __init__(self) -> None:
            self.jobs: list[tuple[object, dict[str, object]]] = []
            self.listeners: list[tuple[object, object]] = []

        def add_job(self, func: object, **kwargs) -> None:
            self.jobs.append((func, kwargs))

        def add_listener(self, callback: object, mask: object) -> None:
            self.listeners.append((callback, mask))

    monkeypatch.setattr(background_scheduler, "AsyncIOScheduler", FakeScheduler)
    settings = _settings(
        stale_worker_reaper_interval_seconds=11,
        orphaned_job_requeue_interval_seconds=22,
        sbatch_submission_interval_seconds=33,
    )

    built = background_scheduler.build_background_scheduler(settings)

    assert isinstance(built, FakeScheduler)
    assert [job[1]["id"] for job in built.jobs] == [
        "stale_worker_reaper",
        "orphaned_job_requeue",
        "sbatch_submission",
    ]
    assert built.jobs[0][0] is background_scheduler.stale_worker_reaper_job
    assert built.jobs[0][1]["args"] == [settings]
    assert built.jobs[1][0] is background_scheduler.orphaned_job_requeue_once
    assert "args" not in built.jobs[1][1]
    assert built.jobs[2][0] is background_scheduler.sbatch_submission_job
    assert built.jobs[2][1]["args"] == [settings]
    assert len(built.listeners) == 1
    assert built.listeners[0][0] is background_scheduler._log_scheduler_job_error
    assert built.listeners[0][1] == background_scheduler.EVENT_JOB_ERROR


@pytest.mark.asyncio
async def test_scheduling_assign_job_for_requesting_worker_passes_args(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = object()

    class FakeAssignmentService:
        def __init__(
            self,
            session: object,
            *,
            heartbeat_interval_seconds: int,
            heartbeat_timeout_multiplier: float,
        ) -> None:
            captured["session"] = session
            captured["interval"] = heartbeat_interval_seconds
            captured["timeout_multiplier"] = heartbeat_timeout_multiplier

        async def assign_job_for_requesting_worker(self, *, requesting_worker_id) -> object:
            captured["worker_id"] = requesting_worker_id
            return expected

    monkeypatch.setattr(scheduling, "AssignmentService", FakeAssignmentService)
    session = cast(AsyncSession, object())
    worker_id = uuid4()

    result = await scheduling.assign_job_for_requesting_worker(
        session,
        heartbeat_interval_seconds=9,
        heartbeat_timeout_multiplier=2.5,
        requesting_worker_id=worker_id,
    )

    assert result is expected
    assert captured == {
        "session": session,
        "interval": 9,
        "timeout_multiplier": 2.5,
        "worker_id": worker_id,
    }


@pytest.mark.asyncio
async def test_scheduling_assign_job_passes_args(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = object()

    class FakeAssignmentService:
        def __init__(
            self,
            session: object,
            *,
            heartbeat_interval_seconds: int,
            heartbeat_timeout_multiplier: float,
        ) -> None:
            captured["session"] = session
            captured["interval"] = heartbeat_interval_seconds
            captured["timeout_multiplier"] = heartbeat_timeout_multiplier

        async def assign_next_job(self) -> object:
            return expected

    monkeypatch.setattr(scheduling, "AssignmentService", FakeAssignmentService)
    session = cast(AsyncSession, object())

    result = await scheduling.assign_job(
        session,
        heartbeat_interval_seconds=12,
        heartbeat_timeout_multiplier=4,
    )

    assert result is expected
    assert captured == {
        "session": session,
        "interval": 12,
        "timeout_multiplier": 4,
    }


@pytest.mark.asyncio
async def test_scheduler_assign_job_passes_settings_to_service(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = object()

    async def fake_assign_job(
        session: AsyncSession,
        *,
        heartbeat_interval_seconds: int,
        heartbeat_timeout_multiplier: float,
    ) -> object:
        captured["session"] = session
        captured["interval"] = heartbeat_interval_seconds
        captured["timeout_multiplier"] = heartbeat_timeout_multiplier
        return expected

    monkeypatch.setattr(scheduler.scheduling, "assign_job", fake_assign_job)
    session = cast(AsyncSession, object())
    settings = _settings(heartbeat_interval_seconds=6, heartbeat_timeout_multiplier=1.2)

    result = await scheduler.assign_job(session, settings)

    assert result is expected
    assert captured == {
        "session": session,
        "interval": 6,
        "timeout_multiplier": 1.2,
    }


@pytest.mark.asyncio
async def test_stale_worker_reaper_job_invokes_both_steps(monkeypatch) -> None:
    settings = _settings()
    reap = AsyncMock(return_value=0)
    autoscale = AsyncMock(return_value=None)
    monkeypatch.setattr(scheduler, "reap_stale_workers", reap)
    monkeypatch.setattr(scheduler, "apply_salad_autoscaling_policy", autoscale)

    await scheduler.stale_worker_reaper_job(settings)

    reap.assert_awaited_once_with(settings)
    autoscale.assert_awaited_once_with(settings)


@pytest.mark.asyncio
async def test_stale_worker_reaper_job_ignores_autoscaling_exceptions(monkeypatch) -> None:
    settings = _settings()
    reap = AsyncMock(return_value=0)
    autoscale = AsyncMock(side_effect=RuntimeError("salad API down"))
    warning = Mock()
    monkeypatch.setattr(scheduler, "reap_stale_workers", reap)
    monkeypatch.setattr(scheduler, "apply_salad_autoscaling_policy", autoscale)
    monkeypatch.setattr(scheduler.LOG, "warning", warning)

    await scheduler.stale_worker_reaper_job(settings)

    reap.assert_awaited_once_with(settings)
    autoscale.assert_awaited_once_with(settings)
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_apply_salad_autoscaling_policy_uses_service(monkeypatch) -> None:
    apply = AsyncMock(return_value=None)

    class FakeSaladAutoscalingService:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def apply(self) -> None:
            await apply()

    monkeypatch.setattr(scheduler, "SaladAutoscalingService", FakeSaladAutoscalingService)
    settings = _settings()

    await scheduler.apply_salad_autoscaling_policy(settings)

    apply.assert_awaited_once()


@pytest.mark.asyncio
async def test_orphaned_job_requeue_once_uses_worker_lifecycle_service(monkeypatch) -> None:
    requeue_once = AsyncMock(return_value=None)
    fake_session = object()

    class FakeWorkerLifecycleService:
        def __init__(self, session: object) -> None:
            assert session is fake_session

        async def requeue_orphaned_jobs_once(self) -> None:
            await requeue_once()

    monkeypatch.setattr(
        scheduler,
        "get_sessionmaker",
        lambda: lambda: _SessionContextManager(fake_session),
    )
    monkeypatch.setattr(scheduler, "WorkerLifecycleService", FakeWorkerLifecycleService)

    await scheduler.orphaned_job_requeue_once()

    requeue_once.assert_awaited_once()


def test_pending_slurm_job_marker_delegates(monkeypatch) -> None:
    marker = Mock(return_value="cluster:123")
    monkeypatch.setattr(scheduler, "pending_slurm_job_marker", marker)

    result = scheduler._pending_slurm_job_marker("cluster", "123")

    assert result == "cluster:123"
    marker.assert_called_once_with("cluster", "123")


@pytest.mark.asyncio
async def test_sbatch_submission_job_runs_pending_submission(monkeypatch) -> None:
    submit = AsyncMock(return_value=2)
    monkeypatch.setattr(scheduler, "submit_pending_slurm_jobs", submit)
    settings = _settings()

    await scheduler.sbatch_submission_job(settings)

    submit.assert_awaited_once_with(settings)


@pytest.mark.asyncio
async def test_sbatch_submission_job_logs_submit_failures(monkeypatch) -> None:
    submit = AsyncMock(side_effect=RuntimeError("sbatch failed"))
    exception = Mock()
    monkeypatch.setattr(scheduler, "submit_pending_slurm_jobs", submit)
    monkeypatch.setattr(scheduler.LOG, "exception", exception)
    settings = _settings()

    await scheduler.sbatch_submission_job(settings)

    submit.assert_awaited_once_with(settings)
    exception.assert_called_once_with("sbatch_submission_failed")
