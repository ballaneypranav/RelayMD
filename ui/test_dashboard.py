from __future__ import annotations

from datetime import UTC, datetime

from ui.dashboard import _build_jobs_dataframe, _build_workers_dataframe


def test_build_jobs_dataframe_includes_required_columns_and_computed_fields() -> None:
    now = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
    jobs = [
        {
            "title": "protein-folding",
            "status": "running",
            "assigned_worker_id": "0a05f971-0f5b-46cb-bd86-d13133f998aa",
            "last_checkpoint_at": "2026-02-24T11:58:45Z",
        }
    ]

    df = _build_jobs_dataframe(jobs, now)

    assert list(df.columns) == [
        "title",
        "status",
        "assigned_worker_id",
        "last_checkpoint_at",
        "time_since_checkpoint",
    ]
    assert len(df) == 1
    assert df.loc[0, "assigned_worker_id"] == "0a05f971..."
    assert df.loc[0, "time_since_checkpoint"] == "1m 15s"


def test_build_workers_dataframe_marks_stale_workers() -> None:
    now = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
    workers = [
        {
            "platform": "salad",
            "gpu_model": "NVIDIA A100",
            "gpu_count": 1,
            "vram_gb": 80,
            "last_heartbeat": "2026-02-24T11:57:30Z",
        },
        {
            "platform": "hpc",
            "gpu_model": "NVIDIA H100",
            "gpu_count": 4,
            "vram_gb": 320,
            "last_heartbeat": "2026-02-24T11:59:50Z",
        },
    ]

    df = _build_workers_dataframe(workers, now)

    assert list(df.columns) == [
        "platform",
        "gpu_model",
        "gpu_count",
        "vram_gb",
        "last_heartbeat",
        "status",
    ]
    assert len(df) == 2
    assert df.loc[0, "status"] == "stale"
    assert df.loc[1, "status"] == "active"
