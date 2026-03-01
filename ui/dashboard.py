from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd  # type: ignore[reportMissingImports]
import streamlit as st  # type: ignore[reportMissingImports]
from streamlit_autorefresh import st_autorefresh  # type: ignore[reportMissingImports]

DEFAULT_ORCHESTRATOR_URL = "http://localhost:8000"
DEFAULT_REFRESH_INTERVAL_SECONDS = 30
STALE_WORKER_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 15.0

JOB_STATUS_STYLES = {
    "completed": ("#d4edda", "#0f5132"),
    "running": ("#fff3cd", "#664d03"),
    "failed": ("#f8d7da", "#842029"),
    "queued": ("#e9ecef", "#1f2937"),
    "assigned": ("#e9ecef", "#1f2937"),
}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_duration(delta_seconds: float) -> str:
    total_seconds = max(int(delta_seconds), 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds}s"


def _truncate_uuid(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value)
    return text if len(text) <= 12 else f"{text[:8]}..."


def _fetch_json(orchestrator_url: str, token: str, path: str, *, expect_list: bool = True) -> Any:
    with httpx.Client(base_url=orchestrator_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(path, headers=_api_headers(token))
        response.raise_for_status()
        payload = response.json()

    if expect_list and not isinstance(payload, list):
        raise ValueError(f"Expected list response for {path}, got {type(payload).__name__}")
    return payload


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-API-Token": token,
    }


def _load_cli_config_values() -> tuple[str, str]:
    try:
        from relaymd.cli.config import CliSettings
    except Exception:  # pragma: no cover - defensive fallback when CLI package import fails
        return DEFAULT_ORCHESTRATOR_URL, ""

    try:
        # Read local env/YAML config only; UI should not block on external secret hydration.
        settings = CliSettings()
    except Exception:  # pragma: no cover - defensive fallback on config loading failures
        return DEFAULT_ORCHESTRATOR_URL, ""

    api_token = "" if settings.api_token == "change-me" else settings.api_token
    return settings.orchestrator_url.rstrip("/"), api_token


def _resolve_runtime_settings() -> tuple[str, str, int]:
    orchestrator_url_env = os.getenv("RELAYMD_ORCHESTRATOR_URL")
    api_token_env = os.getenv("RELAYMD_API_TOKEN") or os.getenv("API_TOKEN")

    orchestrator_url = DEFAULT_ORCHESTRATOR_URL
    api_token = ""
    if orchestrator_url_env is None or not api_token_env:
        orchestrator_url, api_token = _load_cli_config_values()

    if orchestrator_url_env:
        orchestrator_url = orchestrator_url_env
    if api_token_env:
        api_token = api_token_env

    refresh_interval_seconds = int(
        os.getenv("RELAYMD_REFRESH_INTERVAL_SECONDS", str(DEFAULT_REFRESH_INTERVAL_SECONDS))
    )
    refresh_interval_seconds = max(refresh_interval_seconds, 1)
    return orchestrator_url.rstrip("/"), api_token, refresh_interval_seconds


def _cancel_job(orchestrator_url: str, token: str, job_id: str) -> tuple[bool, str]:
    with httpx.Client(base_url=orchestrator_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.delete(
            f"/jobs/{job_id}",
            headers=_api_headers(token),
            params={"force": True},
        )
    if response.status_code == 204:
        return True, "Job cancelled"
    return False, f"Cancel failed ({response.status_code}): {response.text}"


def _requeue_job(orchestrator_url: str, token: str, job: dict[str, Any]) -> tuple[bool, str]:
    payload: dict[str, Any] = {
        "title": f"{job.get('title', 'job')} (re-queued)",
        "input_bundle_path": job.get("input_bundle_path"),
    }
    latest_checkpoint_path = job.get("latest_checkpoint_path")
    if latest_checkpoint_path is not None:
        payload["latest_checkpoint_path"] = latest_checkpoint_path

    with httpx.Client(base_url=orchestrator_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.post("/jobs", headers=_api_headers(token), json=payload)
    if response.is_success:
        try:
            created_job = response.json()
            return True, f"Created job {created_job.get('id', '<unknown id>')}"
        except ValueError:
            return True, "Created re-queued job"
    return False, f"Re-queue failed ({response.status_code}): {response.text}"


def _job_row_style(status: str, row_length: int) -> list[str]:
    background, text = JOB_STATUS_STYLES.get(status, ("#ffffff", "#111827"))
    return [f"background-color: {background}; color: {text}"] * row_length


def _build_jobs_dataframe(raw_jobs: list[dict[str, Any]], now: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for job in raw_jobs:
        checkpoint_at = _parse_datetime(job.get("last_checkpoint_at"))
        if checkpoint_at is None:
            time_since_checkpoint = "-"
            checkpoint_str = "-"
        else:
            checkpoint_str = checkpoint_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            time_since_checkpoint = _format_duration((now - checkpoint_at).total_seconds())

        rows.append(
            {
                "title": job.get("title", "-"),
                "status": str(job.get("status", "-")),
                "assigned_worker_id": _truncate_uuid(job.get("assigned_worker_id")),
                "last_checkpoint_at": checkpoint_str,
                "time_since_checkpoint": time_since_checkpoint,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "title",
            "status",
            "assigned_worker_id",
            "last_checkpoint_at",
            "time_since_checkpoint",
        ],
    )


def _worker_row_style(status: str, row_length: int) -> list[str]:
    if status == "stale":
        return ["background-color: #f8d7da"] * row_length
    if status == "provisioning":
        return ["background-color: #fff3cd; color: #856404"] * row_length
    return [""] * row_length


def _build_workers_dataframe(raw_workers: list[dict[str, Any]], now: datetime) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for worker in raw_workers:
        heartbeat_at = _parse_datetime(worker.get("last_heartbeat"))
        if heartbeat_at is None:
            heartbeat_str = "-"
            status = "stale"
        else:
            heartbeat_str = heartbeat_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            age_seconds = (now - heartbeat_at).total_seconds()
            status = "stale" if age_seconds > STALE_WORKER_SECONDS else "active"

        slurm_id = str(worker.get("provider_id") or "")
        worker_status = str(worker.get("status") or "active")
        if worker_status == "queued":
            status = "provisioning"

        rows.append(
            {
                "platform": str(worker.get("platform", "-")),
                "gpu_model": worker.get("gpu_model", "-"),
                "provider_id": slurm_id or "-",
                "last_heartbeat": heartbeat_str,
                "status": status,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "platform",
            "gpu_model",
            "provider_id",
            "last_heartbeat",
            "status",
        ],
    )


def main() -> None:
    st.set_page_config(page_title="RelayMD Operator Dashboard", layout="wide")

    orchestrator_url, api_token, refresh_interval_seconds = _resolve_runtime_settings()

    if not api_token:
        st.error("RELAYMD_API_TOKEN is required.")
        st.stop()

    # Fetch all data early to show warnings at the top
    now = datetime.now(UTC)
    raw_jobs: list[dict[str, Any]] = []
    raw_workers: list[dict[str, Any]] = []
    raw_clusters: list[dict[str, Any]] = []
    health: dict[str, Any] = {}
    try:
        raw_jobs = _fetch_json(orchestrator_url, api_token, "/jobs")
        raw_workers = _fetch_json(orchestrator_url, api_token, "/workers")
        raw_clusters = _fetch_json(
            orchestrator_url, api_token, "/config/slurm-clusters", expect_list=False
        ).get("clusters", [])
        health = _fetch_json(orchestrator_url, api_token, "/healthz", expect_list=False)
    except Exception as exc:
        st.error(f"Failed to fetch dashboard data: {exc}")
        st.stop()

    # Display system warnings at the very top
    for warn in health.get("warnings", []):
        st.warning(warn)

    st.title("RelayMD Operator Dashboard")
    st.caption(f"Orchestrator: {orchestrator_url}")
    st.caption(f"Refresh interval: {refresh_interval_seconds}s")

    st_autorefresh(interval=refresh_interval_seconds * 1000, key="relaymd-dashboard-refresh")

    jobs_placeholder = st.empty()
    clusters_placeholder = st.empty()
    workers_placeholder = st.empty()

    jobs_df = _build_jobs_dataframe(raw_jobs, now)
    workers_df = _build_workers_dataframe(raw_workers, now)

    with jobs_placeholder.container():
        st.subheader("Jobs")
        styled_jobs = jobs_df.style.apply(
            lambda row: _job_row_style(str(row["status"]), len(row)),
            axis=1,
        )
        st.dataframe(styled_jobs, width="stretch", hide_index=True)

    with clusters_placeholder.container():
        st.subheader("Cluster Configs")
        clusters_df = pd.DataFrame(
            raw_clusters,
            columns=[
                "name",
                "partition",
                "strategy",
                "max_pending_jobs",
                "wall_time",
            ],
        )
        st.dataframe(clusters_df, width="stretch", hide_index=True)

    with workers_placeholder.container():
        st.subheader("Workers")
        styled_workers = workers_df.style.apply(
            lambda row: _worker_row_style(str(row["status"]), len(row)),
            axis=1,
        )
        st.dataframe(styled_workers, width="stretch", hide_index=True)

    st.divider()
    st.subheader("Manual Controls")
    st.info(
        "No drain worker button is provided. To drain workers, cancel assigned jobs; "
        "workers stop naturally on their next poll cycle."
    )

    cancelable_jobs = [job for job in raw_jobs if str(job.get("status")) in {"queued", "running"}]
    requeue_jobs = [job for job in raw_jobs if str(job.get("status")) in {"failed", "cancelled"}]

    st.markdown("### Cancel Job")
    cancel_selected = st.selectbox(
        "Cancelable jobs",
        options=cancelable_jobs,
        format_func=lambda job: f"{job.get('title', '<untitled>')} [{job.get('status', '-')}]",
        key="cancel_job_select",
        disabled=not cancelable_jobs,
    )
    if st.button("Cancel", disabled=not cancelable_jobs):
        st.session_state["cancel_pending_job"] = cancel_selected

    pending_cancel = st.session_state.get("cancel_pending_job")
    if pending_cancel is not None:
        title = str(pending_cancel.get("title", "<untitled>"))
        st.warning(f"Cancel job '{title}'? This cannot be undone.")
        confirm_col, abort_col = st.columns(2)
        with confirm_col:
            if st.button("Confirm", key="cancel_confirm"):
                ok, message = _cancel_job(
                    orchestrator_url=orchestrator_url,
                    token=api_token,
                    job_id=str(pending_cancel["id"]),
                )
                if ok:
                    st.success(message)
                else:
                    st.error(message)
                st.session_state["cancel_pending_job"] = None
        with abort_col:
            if st.button("Abort", key="cancel_abort"):
                st.session_state["cancel_pending_job"] = None

    st.markdown("### Re-queue Job")
    requeue_selected = st.selectbox(
        "Failed or cancelled jobs",
        options=requeue_jobs,
        format_func=lambda job: f"{job.get('title', '<untitled>')} [{job.get('status', '-')}]",
        key="requeue_job_select",
        disabled=not requeue_jobs,
    )
    if st.button("Re-queue", disabled=not requeue_jobs):
        # Cancellation is state-only for running jobs: workers finish current chunk,
        # may still POST /jobs/{id}/complete, orchestrator discards it for cancelled jobs,
        # and workers then exit naturally on the next /jobs/request poll cycle.
        ok, message = _requeue_job(
            orchestrator_url=orchestrator_url,
            token=api_token,
            job=requeue_selected,
        )
        if ok:
            st.success(message)
        else:
            st.error(message)


if __name__ == "__main__":
    main()
