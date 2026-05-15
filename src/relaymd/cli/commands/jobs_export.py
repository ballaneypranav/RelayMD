from __future__ import annotations

from datetime import UTC, datetime
from numbers import Real
from typing import Any
from zoneinfo import ZoneInfo

JOB_EXPORT_COLUMNS: list[str] = [
    "id",
    "job_id",
    "title",
    "status",
    "age",
    "time_in_status",
    "assigned_worker_id",
    "time_since_checkpoint",
    "progress",
    "checkpoint_health",
    "job_id_full",
    "assigned_worker_full",
    "created_at_iso",
    "assigned_at_iso",
    "started_at_iso",
    "status_changed_at_iso",
    "runtime",
    "total_runtime",
    "etc",
    "updated_at_iso",
    "input_bundle",
    "pinned_clusters",
    "comment_text",
    "queue_blocked",
    "progress_percent",
    "progress_codes_text",
    "latest_checkpoint",
    "checkpoint_cycle_status_text",
    "checkpoint_failures_text",
    "history_source",
    "checkpoint_age",
]

_QUEUE_BLOCKED_LABELS: dict[str, str] = {
    "no_enabled_pinned_clusters": "Pinned clusters disabled",
    "no_matching_pinned_clusters": "Pinned clusters unavailable",
}
_DURATION_MAX_PARTS = 2
_TRUNCATE_ID_LENGTH = 12
_TRUNCATE_ID_PREFIX = 8
_TZ_OFFSET_SUFFIX_LENGTH = 6
_EASTERN_TZ = ZoneInfo("America/New_York")


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    has_utc_designator = text.endswith(("Z", "z"))
    has_offset = len(text) >= _TZ_OFFSET_SUFFIX_LENGTH and text[-_TZ_OFFSET_SUFFIX_LENGTH] in {
        "+",
        "-",
    }
    normalized = text if has_utc_designator or has_offset else f"{text}Z"
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _progress_as_float(raw_value: Any) -> float:
    if raw_value is None or raw_value == "":
        return 0.0
    if isinstance(raw_value, bool):
        return 1.0 if raw_value else 0.0
    if isinstance(raw_value, Real):
        return float(raw_value)
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
    if not isinstance(raw_value, str) or not raw_value:
        return 0.0
    try:
        return float(raw_value)
    except ValueError:
        return 0.0


def format_duration(delta_seconds: float) -> str:
    total_seconds = max(int(delta_seconds), 0)
    units: list[tuple[str, int]] = [
        ("mo", 30 * 24 * 60 * 60),
        ("d", 24 * 60 * 60),
        ("h", 60 * 60),
        ("m", 60),
    ]
    parts: list[str] = []
    remainder = total_seconds
    for suffix, unit_seconds in units:
        value = remainder // unit_seconds
        remainder %= unit_seconds
        if value > 0:
            parts.append(f"{value}{suffix}")
    if len(parts) >= _DURATION_MAX_PARTS:
        return " ".join(parts[:_DURATION_MAX_PARTS])
    if len(parts) == 1:
        return f"{parts[0]} {remainder}s" if remainder > 0 else parts[0]
    return f"{total_seconds // 60}m {total_seconds % 60}s"


def _format_eastern_timestamp(value: datetime | None) -> str:
    if value is None:
        return "-"
    eastern = value.astimezone(_EASTERN_TZ)
    tz_name = eastern.tzname() or ""
    return f"{eastern.isoformat()} {tz_name}".strip()


def _truncate_id(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value)
    return text if len(text) <= _TRUNCATE_ID_LENGTH else f"{text[:_TRUNCATE_ID_PREFIX]}..."


def _runtime_seconds(job: dict[str, Any], now: datetime) -> float:
    started_at = parse_timestamp(job.get("started_at"))
    assigned_at = parse_timestamp(job.get("assigned_at"))
    status_changed_at = parse_timestamp(job.get("status_changed_at"))
    start = started_at or assigned_at
    if start is None:
        return 0.0
    status = str(job.get("status") or "")
    if status in {"assigned", "running"}:
        return max((now - start).total_seconds(), 0.0)
    if status_changed_at is None:
        return 0.0
    return max((status_changed_at - start).total_seconds(), 0.0)


def _eta_seconds(job: dict[str, Any], now: datetime) -> float | None:
    if str(job.get("status") or "") not in {"assigned", "running"}:
        return None
    progress = max(0.0, min(1.0, _progress_as_float(job.get("progress"))))
    if progress <= 0 or progress >= 1:
        return None
    runtime = _runtime_seconds(job, now)
    return max((runtime / progress) - runtime, 0.0)


def job_to_export_row(job: dict[str, Any], now: datetime) -> dict[str, str]:
    created_at = parse_timestamp(job.get("created_at"))
    assigned_at = parse_timestamp(job.get("assigned_at"))
    started_at = parse_timestamp(job.get("started_at"))
    status_changed_at = parse_timestamp(job.get("status_changed_at"))
    updated_at = parse_timestamp(job.get("updated_at"))
    checkpoint_at = parse_timestamp(job.get("last_checkpoint_at"))
    runtime_seconds = _runtime_seconds(job, now)
    eta_seconds = _eta_seconds(job, now)
    progress_value = _progress_as_float(job.get("progress"))
    progress_percent = round(progress_value * 1000) / 10
    preferred_clusters = job.get("preferred_clusters") or []
    progress_codes = job.get("progress_codes") or []
    failures = job.get("checkpoint_cycle_failures") or []
    queue_blocked_reason = str(job.get("queue_blocked_reason") or "")

    pinned_clusters = (
        ", ".join(str(cluster) for cluster in preferred_clusters)
        if isinstance(preferred_clusters, list)
        else str(preferred_clusters)
    )
    progress_codes_text = (
        ", ".join(str(code) for code in progress_codes)
        if isinstance(progress_codes, list)
        else str(progress_codes)
    )
    checkpoint_failures_text = (
        "; ".join(
            f"{failure.get('code', '-')}: {failure.get('detail', '-')}"
            for failure in failures
            if isinstance(failure, dict)
        )
        if isinstance(failures, list) and failures
        else "-"
    )

    return {
        "id": str(job.get("id") or "-"),
        "job_id": _truncate_id(job.get("id")),
        "title": str(job.get("title") or "-"),
        "status": str(job.get("status") or "-"),
        "age": format_duration((now - created_at).total_seconds()) if created_at else "-",
        "time_in_status": format_duration((now - status_changed_at).total_seconds())
        if status_changed_at
        else "-",
        "assigned_worker_id": _truncate_id(job.get("assigned_worker_id")),
        "time_since_checkpoint": format_duration((now - checkpoint_at).total_seconds())
        if checkpoint_at
        else "-",
        "progress": f"{progress_percent}%",
        "checkpoint_health": "warn" if isinstance(failures, list) and failures else "ok",
        "job_id_full": str(job.get("id") or "-"),
        "assigned_worker_full": str(job.get("assigned_worker_id") or "-"),
        "created_at_iso": _format_eastern_timestamp(created_at),
        "assigned_at_iso": _format_eastern_timestamp(assigned_at),
        "started_at_iso": _format_eastern_timestamp(started_at),
        "status_changed_at_iso": _format_eastern_timestamp(status_changed_at),
        "runtime": format_duration(runtime_seconds),
        "total_runtime": format_duration(runtime_seconds),
        "etc": format_duration(eta_seconds) if eta_seconds is not None else "-",
        "updated_at_iso": _format_eastern_timestamp(updated_at),
        "input_bundle": str(job.get("input_bundle_path") or "-"),
        "pinned_clusters": pinned_clusters or "-",
        "comment_text": str(job.get("comment") or "-"),
        "queue_blocked": _QUEUE_BLOCKED_LABELS.get(queue_blocked_reason, queue_blocked_reason)
        if str(job.get("status") or "") == "queued" and queue_blocked_reason
        else "-",
        "progress_percent": f"{progress_percent}%",
        "progress_codes_text": progress_codes_text or "-",
        "latest_checkpoint": str(
            job.get("latest_checkpoint_manifest_path") or job.get("latest_checkpoint_path") or "-"
        ),
        "checkpoint_cycle_status_text": str(job.get("checkpoint_cycle_status") or "-"),
        "checkpoint_failures_text": checkpoint_failures_text,
        "history_source": "Unavailable",
        "checkpoint_age": format_duration((now - checkpoint_at).total_seconds())
        if checkpoint_at
        else "-",
    }
