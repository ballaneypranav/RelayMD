from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from relaymd.models import JobHistoryEventRead

from relaymd.orchestrator.services.job_history_service import build_worker_runtime


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)


def test_worker_deregistered_requeue_closes_runtime_segment() -> None:
    worker_id = uuid4()
    events = [
        JobHistoryEventRead(
            occurred_at=_dt("2026-01-01T12:00:00+00:00"),
            event_seq=1,
            event_type="assigned",
            worker_id=worker_id,
        ),
        JobHistoryEventRead(
            occurred_at=_dt("2026-01-01T12:30:00+00:00"),
            event_seq=2,
            event_type="worker_deregistered_requeue",
            worker_id=worker_id,
        ),
    ]

    segments, totals = build_worker_runtime(events, now=_dt("2026-01-01T14:00:00+00:00"))
    assert len(segments) == 1
    assert segments[0].open is False
    assert segments[0].duration_seconds == 30 * 60
    assert segments[0].worker_id == worker_id

    assert len(totals) == 1
    assert totals[0].worker_id == worker_id
    assert totals[0].total_runtime_seconds == 30 * 60


def test_running_event_takes_precedence_over_assigned_for_segment_start() -> None:
    worker_id = uuid4()
    events = [
        JobHistoryEventRead(
            occurred_at=_dt("2026-01-01T12:00:00+00:00"),
            event_seq=1,
            event_type="assigned",
            worker_id=worker_id,
        ),
        JobHistoryEventRead(
            occurred_at=_dt("2026-01-01T12:10:00+00:00"),
            event_seq=2,
            event_type="running",
            worker_id=worker_id,
        ),
        JobHistoryEventRead(
            occurred_at=_dt("2026-01-01T13:00:00+00:00"),
            event_seq=3,
            event_type="completed",
            worker_id=worker_id,
        ),
    ]

    segments, totals = build_worker_runtime(events, now=_dt("2026-01-01T14:00:00+00:00"))
    assert len(segments) == 1
    assert segments[0].started_at == _dt("2026-01-01T12:10:00+00:00")
    assert segments[0].ended_at == _dt("2026-01-01T13:00:00+00:00")
    assert segments[0].duration_seconds == 50 * 60
    assert segments[0].worker_id == worker_id

    assert len(totals) == 1
    assert totals[0].worker_id == worker_id
    assert totals[0].total_runtime_seconds == 50 * 60
