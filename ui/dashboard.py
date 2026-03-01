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


def _render_offline_state(
    orchestrator_url: str,
    refresh_interval_seconds: int,
    exc: Exception,
) -> None:
    """Render a clear 'orchestrator unreachable' panel instead of a bare st.error."""
    now = datetime.now(UTC)

    # Record the first time we noticed the outage.
    if "orchestrator_offline_since" not in st.session_state:
        st.session_state["orchestrator_offline_since"] = now
    offline_since: datetime = st.session_state["orchestrator_offline_since"]
    offline_duration = _format_duration((now - offline_since).total_seconds())

    # Keep auto-refreshing so the dashboard recovers the moment the orchestrator comes back.
    st_autorefresh(interval=refresh_interval_seconds * 1000, key="relaymd-dashboard-refresh")

    st.title("RelayMD Operator Dashboard")
    st.error("Orchestrator unreachable", icon="\U0001f534")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("URL", orchestrator_url)
    with col2:
        st.metric("Offline for", offline_duration)

    with st.expander("Error details", expanded=True):
        st.code(str(exc), language=None)

    st.caption(
        f"Retrying every {refresh_interval_seconds}s. "
        "Start the orchestrator (e.g. start the tmux session) to restore service."
    )


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
    job_id = job.get("id")
    with httpx.Client(base_url=orchestrator_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.post(f"/jobs/{job_id}/requeue", headers=_api_headers(token))
    if response.is_success:
        try:
            created_job = response.json()
            return True, f"Re-queued as job {created_job.get('id', '<unknown id>')}"
        except ValueError:
            return True, "Job re-queued"
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
        else:
            time_since_checkpoint = _format_duration((now - checkpoint_at).total_seconds())

        created_at = _parse_datetime(job.get("created_at"))
        age = _format_duration((now - created_at).total_seconds()) if created_at else "-"

        updated_at = _parse_datetime(job.get("updated_at"))
        time_in_status = _format_duration((now - updated_at).total_seconds()) if updated_at else "-"

        rows.append(
            {
                "job_id": _truncate_uuid(job.get("id")),
                "title": job.get("title", "-"),
                "status": str(job.get("status", "-")),
                "age": age,
                "time_in_status": time_in_status,
                "assigned_worker_id": _truncate_uuid(job.get("assigned_worker_id")),
                "time_since_checkpoint": time_since_checkpoint,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "job_id",
            "title",
            "status",
            "age",
            "time_in_status",
            "assigned_worker_id",
            "time_since_checkpoint",
        ],
    )


def _worker_row_style(status: str, row_length: int) -> list[str]:
    if status == "stale":
        return ["background-color: #f8d7da"] * row_length
    if status == "provisioning":
        return ["background-color: #fff3cd; color: #856404"] * row_length
    return [""] * row_length


def _build_workers_dataframe(
    raw_workers: list[dict[str, Any]],
    now: datetime,
    raw_jobs: list[dict[str, Any]] | None = None,
) -> pd.DataFrame:
    # Build worker_id -> job label mapping for active assignments
    worker_job: dict[str, str] = {}
    for job in raw_jobs or []:
        wid = str(job.get("assigned_worker_id") or "")
        if wid and str(job.get("status")) in {"running", "assigned"}:
            jid = _truncate_uuid(job.get("id"))
            title = str(job.get("title") or "")[:24]
            worker_job[wid] = f"{title} ({jid})"

    rows: list[dict[str, Any]] = []
    for worker in raw_workers:
        heartbeat_at = _parse_datetime(worker.get("last_heartbeat"))
        if heartbeat_at is None:
            heartbeat_str = "-"
            status = "stale"
        else:
            heartbeat_str = heartbeat_at.strftime("%H:%M:%S UTC")
            age_seconds = (now - heartbeat_at).total_seconds()
            status = "stale" if age_seconds > STALE_WORKER_SECONDS else "active"

        registered_at = _parse_datetime(worker.get("registered_at"))
        uptime = _format_duration((now - registered_at).total_seconds()) if registered_at else "-"

        slurm_id = str(worker.get("provider_id") or "")
        worker_status = str(worker.get("status") or "active")
        if worker_status == "queued":
            status = "provisioning"

        gpu_count = worker.get("gpu_count", "-")
        vram_gb = worker.get("vram_gb")
        gpu_spec = (
            f"{gpu_count}x {worker.get('gpu_model', '?')} ({vram_gb} GB)"
            if vram_gb is not None
            else str(worker.get("gpu_model", "-"))
        )

        worker_id_str = str(worker.get("id") or "")
        current_job = worker_job.get(worker_id_str, "-")

        rows.append(
            {
                "platform": str(worker.get("platform", "-")),
                "gpu": gpu_spec,
                "provider_id": slurm_id or "-",
                "uptime": uptime,
                "last_heartbeat": heartbeat_str,
                "current_job": current_job,
                "status": status,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "platform",
            "gpu",
            "provider_id",
            "uptime",
            "last_heartbeat",
            "current_job",
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
        _render_offline_state(orchestrator_url, refresh_interval_seconds, exc)
        st.stop()

    # Orchestrator is reachable — clear any recorded outage time.
    st.session_state.pop("orchestrator_offline_since", None)

    # Display system warnings at the very top
    for warn in health.get("warnings", []):
        st.warning(warn)

    st.title("RelayMD Operator Dashboard")
    st.caption(f"Orchestrator: {orchestrator_url} · Refresh: {refresh_interval_seconds}s")

    # --- Summary metrics strip ---
    status_counts: dict[str, int] = {}
    for job in raw_jobs:
        s = str(job.get("status", "unknown"))
        status_counts[s] = status_counts.get(s, 0) + 1

    active_workers = sum(1 for w in raw_workers if str(w.get("status") or "active") != "queued")
    provisioning_workers = sum(
        1 for w in raw_workers if str(w.get("status") or "active") == "queued"
    )

    mc1, mc2, mc3, mc4, mc5, mc6, mc7 = st.columns(7)
    mc1.metric("Queued", status_counts.get("queued", 0))
    mc2.metric("Running", status_counts.get("running", 0))
    mc3.metric("Completed", status_counts.get("completed", 0))
    mc4.metric("Failed", status_counts.get("failed", 0))
    mc5.metric("Cancelled", status_counts.get("cancelled", 0))
    mc6.metric("Active Workers", active_workers)
    mc7.metric("Provisioning", provisioning_workers)

    # Tailscale status strip
    if "tailscale" in health:
        ts = health["tailscale"]
        if ts.get("connected"):
            ts_label = ts.get("hostname") or ts.get("dns_name") or ts.get("ip") or "connected"
            ts_ip = ts.get("ip", "")
            st.success(f"🟢 Tailscale: **{ts_label}** ({ts_ip})", icon=None)
        else:
            ts_error = ts.get("error", "unknown error")
            st.error(f"🔴 Tailscale: not connected — {ts_error}")

    st_autorefresh(interval=refresh_interval_seconds * 1000, key="relaymd-dashboard-refresh")

    st.divider()

    # --- Sidebar: Settings and Manual Controls ---
    with st.sidebar:
        st.header("Settings")
        st.caption(f"**URL:** {orchestrator_url}")
        st.caption(f"**Refresh:** {refresh_interval_seconds}s")

        st.divider()
        st.header("Manual Controls")
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

        st.subheader("Cancel Job")
        cancel_selected = st.selectbox(
            "Cancelable jobs",
            options=cancelable_jobs,
            format_func=lambda job: f"{job.get('title', '<untitled>')} [{job.get('status', '-')}]",
            key="cancel_job_select",
            disabled=not cancelable_jobs,
        )
        if st.button("Cancel", disabled=not cancelable_jobs, key="cancel_job_btn"):
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

        st.subheader("Re-queue Job")
        requeue_selected = st.selectbox(
            "Failed or cancelled jobs",
            options=requeue_jobs,
            format_func=lambda job: f"{job.get('title', '<untitled>')} [{job.get('status', '-')}]",
            key="requeue_job_select",
            disabled=not requeue_jobs,
        )
        if st.button("Re-queue", disabled=not requeue_jobs, key="requeue_job_btn"):
            ok, message = _requeue_job(
                orchestrator_url=orchestrator_url,
                token=api_token,
                job=requeue_selected,
            )
            if ok:
                st.success(message)
            else:
                st.error(message)

    # --- Main content area with tabs ---
    jobs_df = _build_jobs_dataframe(raw_jobs, now)
    workers_df = _build_workers_dataframe(raw_workers, now, raw_jobs)

    tab_jobs, tab_workers, tab_clusters = st.tabs(["Jobs", "Workers", "Cluster Configs"])

    # --- Jobs Tab ---
    with tab_jobs:
        st.subheader("Jobs")

        # Filter by status
        if not jobs_df.empty:
            available_statuses = sorted(jobs_df["status"].unique().tolist())
            selected_statuses = st.multiselect(
                "Filter by status",
                options=available_statuses,
                default=available_statuses,
                key="job_status_filter",
            )
            filtered_jobs_df = (
                jobs_df[jobs_df["status"].isin(selected_statuses)] if selected_statuses else jobs_df
            )
        else:
            filtered_jobs_df = jobs_df

        # Render jobs table with color styling
        if not filtered_jobs_df.empty:
            styled_jobs = filtered_jobs_df.style.apply(
                lambda row: _job_row_style(str(row["status"]), len(row)),
                axis=1,
            )
            st.dataframe(styled_jobs, width="stretch", hide_index=True)
        else:
            st.info("No jobs match the selected filters.")

        # Job detail expander — select any job to inspect full IDs and paths
        if raw_jobs:
            with st.expander("Job details", expanded=False):
                detail_job = st.selectbox(
                    "Select job",
                    options=raw_jobs,
                    format_func=lambda j: (
                        f"{j.get('title', '<untitled>')} [{j.get('status', '-')}]"
                    ),
                    key="detail_job_select",
                )
                if detail_job:
                    d1, d2 = st.columns(2)
                    with d1:
                        st.text_input("Job ID", value=str(detail_job.get("id", "")), disabled=True)
                        st.text_input(
                            "Assigned Worker ID",
                            value=str(detail_job.get("assigned_worker_id") or ""),
                            disabled=True,
                        )
                        created_at = _parse_datetime(detail_job.get("created_at"))
                        st.text_input(
                            "Created at",
                            value=(
                                created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if created_at else "-"
                            ),
                            disabled=True,
                        )
                    with d2:
                        st.text_input(
                            "Input bundle path",
                            value=str(detail_job.get("input_bundle_path") or ""),
                            disabled=True,
                        )
                        st.text_input(
                            "Latest checkpoint path",
                            value=str(detail_job.get("latest_checkpoint_path") or ""),
                            disabled=True,
                        )
                        chk_at = _parse_datetime(detail_job.get("last_checkpoint_at"))
                        st.text_input(
                            "Last checkpoint at",
                            value=(chk_at.strftime("%Y-%m-%d %H:%M:%S UTC") if chk_at else "-"),
                            disabled=True,
                        )

    # --- Workers Tab ---
    with tab_workers:
        st.subheader("Workers")
        styled_workers = workers_df.style.apply(
            lambda row: _worker_row_style(str(row["status"]), len(row)),
            axis=1,
        )
        st.dataframe(styled_workers, width="stretch", hide_index=True)

    # --- Cluster Configs Tab ---
    with tab_clusters:
        st.subheader("Cluster Configs")
        if raw_clusters:
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
        else:
            st.info("No cluster configs available.")


if __name__ == "__main__":
    main()
