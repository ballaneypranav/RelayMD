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

JOB_STATUS_COLORS = {
    "completed": "#d4edda",
    "running": "#fff3cd",
    "failed": "#f8d7da",
    "queued": "#e9ecef",
    "assigned": "#e9ecef",
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


def _fetch_json(orchestrator_url: str, token: str, path: str) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-API-Token": token,
    }
    with httpx.Client(base_url=orchestrator_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(path, headers=headers)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, list):
        raise ValueError(f"Expected list response for {path}, got {type(payload).__name__}")
    return payload


def _api_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-API-Token": token,
    }


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
    color = JOB_STATUS_COLORS.get(status, "#ffffff")
    return [f"background-color: {color}"] * row_length


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

        rows.append(
            {
                "platform": str(worker.get("platform", "-")),
                "gpu_model": worker.get("gpu_model", "-"),
                "gpu_count": worker.get("gpu_count", "-"),
                "vram_gb": worker.get("vram_gb", "-"),
                "last_heartbeat": heartbeat_str,
                "status": status,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "platform",
            "gpu_model",
            "gpu_count",
            "vram_gb",
            "last_heartbeat",
            "status",
        ],
    )


def main() -> None:
    st.set_page_config(page_title="RelayMD Operator Dashboard", layout="wide")
    st.title("RelayMD Operator Dashboard")

    orchestrator_url = os.getenv("RELAYMD_ORCHESTRATOR_URL", DEFAULT_ORCHESTRATOR_URL).rstrip("/")
    api_token = os.getenv("RELAYMD_API_TOKEN", "")
    refresh_interval_seconds = int(
        os.getenv("RELAYMD_REFRESH_INTERVAL_SECONDS", str(DEFAULT_REFRESH_INTERVAL_SECONDS))
    )
    refresh_interval_seconds = max(refresh_interval_seconds, 1)

    st.caption(f"Orchestrator: {orchestrator_url}")
    st.caption(f"Refresh interval: {refresh_interval_seconds}s")

    if not api_token:
        st.error("RELAYMD_API_TOKEN is required.")
        st.stop()

    st_autorefresh(interval=refresh_interval_seconds * 1000, key="relaymd-dashboard-refresh")

    now = datetime.now(UTC)
    jobs_placeholder = st.empty()
    workers_placeholder = st.empty()

    raw_jobs: list[dict[str, Any]] = []
    raw_workers: list[dict[str, Any]] = []
    try:
        raw_jobs = _fetch_json(orchestrator_url, api_token, "/jobs")
        raw_workers = _fetch_json(orchestrator_url, api_token, "/workers")
    except Exception as exc:
        st.error(f"Failed to fetch dashboard data: {exc}")
        st.stop()

    jobs_df = _build_jobs_dataframe(raw_jobs, now)
    workers_df = _build_workers_dataframe(raw_workers, now)

    with jobs_placeholder.container():
        st.subheader("Jobs")
        styled_jobs = jobs_df.style.apply(
            lambda row: _job_row_style(str(row["status"]), len(row)),
            axis=1,
        )
        st.dataframe(styled_jobs, use_container_width=True, hide_index=True)

    with workers_placeholder.container():
        st.subheader("Workers")
        styled_workers = workers_df.style.apply(
            lambda row: _worker_row_style(str(row["status"]), len(row)),
            axis=1,
        )
        st.dataframe(styled_workers, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Manual Controls")
    st.info(
        "No drain worker button is provided. To drain workers, cancel assigned jobs; "
        "workers stop naturally on their next poll cycle."
    )

    cancelable_jobs = [
        job for job in raw_jobs if str(job.get("status")) in {"queued", "running"}
    ]
    requeue_jobs = [
        job for job in raw_jobs if str(job.get("status")) in {"failed", "cancelled"}
    ]

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
