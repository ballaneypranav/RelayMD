from __future__ import annotations

from datetime import UTC, datetime

import pytest


def _import_dashboard_module():
    pytest.importorskip("pandas")
    pytest.importorskip("streamlit")
    pytest.importorskip("streamlit_autorefresh")
    import ui.dashboard as dashboard

    return dashboard


def test_build_jobs_dataframe_includes_required_columns_and_computed_fields() -> None:
    dashboard = _import_dashboard_module()
    now = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
    jobs = [
        {
            "title": "protein-folding",
            "status": "running",
            "assigned_worker_id": "0a05f971-0f5b-46cb-bd86-d13133f998aa",
            "last_checkpoint_at": "2026-02-24T11:58:45Z",
        }
    ]

    df = dashboard._build_jobs_dataframe(jobs, now)

    assert list(df.columns) == [
        "job_id",
        "title",
        "status",
        "age",
        "time_in_status",
        "assigned_worker_id",
        "time_since_checkpoint",
    ]
    assert len(df) == 1
    assert df.loc[0, "assigned_worker_id"] == "0a05f971..."
    assert df.loc[0, "time_since_checkpoint"] == "1m 15s"


@pytest.mark.parametrize(
    ("delta_seconds", "expected"),
    [
        (3, "0m 3s"),
        (23 * 60 + 3, "23m 3s"),
        (66 * 60 + 49, "1h 6m"),
        (25872 * 60 + 19, "17d 23h"),
        ((30 * 24 * 60 + 25) * 60 + 11, "1mo 25m"),
    ],
)
def test_format_duration_uses_larger_units(delta_seconds: int, expected: str) -> None:
    dashboard = _import_dashboard_module()

    assert dashboard._format_duration(delta_seconds) == expected


def test_build_workers_dataframe_marks_stale_workers() -> None:
    dashboard = _import_dashboard_module()
    now = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
    workers = [
        {
            "platform": "salad",
            "gpu_model": "NVIDIA A100",
            "gpu_count": 1,
            "vram_gb": 80,
            "slurm_job_id": None,
            "last_heartbeat": "2026-02-24T11:57:30Z",
        },
        {
            "platform": "hpc",
            "gpu_model": "NVIDIA H100",
            "gpu_count": 4,
            "vram_gb": 320,
            "slurm_job_id": None,
            "last_heartbeat": "2026-02-24T11:59:50Z",
        },
    ]

    df = dashboard._build_workers_dataframe(workers, now)

    assert list(df.columns) == [
        "platform",
        "gpu",
        "provider_id",
        "provider_state",
        "uptime",
        "last_heartbeat",
        "current_job",
        "status",
    ]
    assert len(df) == 2
    assert df.loc[0, "status"] == "stale"
    assert df.loc[1, "status"] == "active"


def test_build_workers_dataframe_marks_provisioning_workers() -> None:
    dashboard = _import_dashboard_module()
    now = datetime(2026, 2, 24, 12, 0, 0, tzinfo=UTC)
    workers = [
        {
            "platform": "hpc",
            "gpu_model": "a100",
            "gpu_count": 2,
            "vram_gb": 0,
            "provider_id": "gilbreth:12345",
            "status": "queued",
            # Old heartbeat — but status should be "provisioning", not "stale"
            "last_heartbeat": "2026-02-24T10:00:00Z",
        }
    ]

    df = dashboard._build_workers_dataframe(workers, now)

    assert len(df) == 1
    assert df.loc[0, "status"] == "provisioning"
    assert df.loc[0, "provider_id"] == "gilbreth:12345"
    assert df.loc[0, "provider_state"] == "-"


def test_resolve_runtime_settings_uses_cli_config_when_env_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboard = _import_dashboard_module()
    monkeypatch.delenv("RELAYMD_ORCHESTRATOR_URL", raising=False)
    monkeypatch.delenv("RELAYMD_API_TOKEN", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("RELAYMD_REFRESH_INTERVAL_SECONDS", raising=False)
    monkeypatch.setattr(
        dashboard,
        "_load_cli_config_values",
        lambda: ("http://config-orchestrator:36158", "config-api-token"),
    )

    orchestrator_url, api_token, refresh_interval_seconds = dashboard._resolve_runtime_settings()

    assert orchestrator_url == "http://config-orchestrator:36158"
    assert api_token == "config-api-token"
    assert refresh_interval_seconds == 30


def test_resolve_runtime_settings_env_overrides_cli_config(monkeypatch: pytest.MonkeyPatch) -> None:
    dashboard = _import_dashboard_module()
    monkeypatch.setenv("RELAYMD_ORCHESTRATOR_URL", "http://env-orchestrator:9000/")
    monkeypatch.setenv("RELAYMD_API_TOKEN", "env-api-token")
    monkeypatch.setenv("RELAYMD_REFRESH_INTERVAL_SECONDS", "5")
    monkeypatch.setattr(
        dashboard,
        "_load_cli_config_values",
        lambda: (_ for _ in ()).throw(AssertionError("should not load CLI settings")),
    )

    orchestrator_url, api_token, refresh_interval_seconds = dashboard._resolve_runtime_settings()

    assert orchestrator_url == "http://env-orchestrator:9000"
    assert api_token == "env-api-token"
    assert refresh_interval_seconds == 5
