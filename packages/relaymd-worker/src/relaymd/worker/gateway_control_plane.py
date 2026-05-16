from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

HTTP_CONFLICT = 409


@dataclass(frozen=True)
class ControlPlaneRequestContext:
    orchestrator_url: str
    api_token: str
    timeout_seconds: float
    proxy_url: str | None


def start_handoff(
    *,
    request_context: ControlPlaneRequestContext,
    job_id: UUID,
    payload: dict[str, object],
) -> bool:
    response = httpx.post(
        f"{request_context.orchestrator_url}/jobs/{job_id}/handoff/start",
        headers={"x-api-token": request_context.api_token},
        json=payload,
        timeout=request_context.timeout_seconds,
        proxy=request_context.proxy_url,
    )
    if response.status_code == HTTP_CONFLICT:
        return False
    response.raise_for_status()
    return True


def complete_handoff(
    *,
    request_context: ControlPlaneRequestContext,
    job_id: UUID,
    payload: dict[str, object],
) -> bool:
    response = httpx.post(
        f"{request_context.orchestrator_url}/jobs/{job_id}/handoff/complete",
        headers={"x-api-token": request_context.api_token},
        json=payload,
        timeout=request_context.timeout_seconds,
        proxy=request_context.proxy_url,
    )
    if response.status_code == HTTP_CONFLICT:
        return False
    response.raise_for_status()
    return True


def is_cancellation_requested(
    *,
    request_context: ControlPlaneRequestContext,
    job_id: UUID,
) -> bool:
    if request_context.proxy_url is None:
        response = httpx.get(
            f"{request_context.orchestrator_url}/jobs/{job_id}/control",
            headers={"x-api-token": request_context.api_token},
            timeout=request_context.timeout_seconds,
        )
    else:
        response = httpx.get(
            f"{request_context.orchestrator_url}/jobs/{job_id}/control",
            headers={"x-api-token": request_context.api_token},
            timeout=request_context.timeout_seconds,
            proxy=request_context.proxy_url,
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("cancellation_requested", False))
