from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from relaymd_api_client import errors as api_errors
from relaymd_api_client.models.http_validation_error import (
    HTTPValidationError as ApiHTTPValidationError,
)

HTTP_CONFLICT = 409


def raise_if_validation_error(response: object) -> None:
    if isinstance(response, ApiHTTPValidationError):
        raise RuntimeError(response.to_dict())


def is_conflict_exception(exc: Exception) -> bool:
    if not isinstance(exc, api_errors.UnexpectedStatus):
        return False
    return exc.status_code == HTTP_CONFLICT


def is_conflict_response(response: object) -> bool:
    if response is None:
        return False
    if getattr(response, "error", None) == "job_transition_conflict":
        return True
    if isinstance(response, dict) and response.get("error") == "job_transition_conflict":
        return True
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        payload = cast(dict[str, object], to_dict())
        return payload.get("error") == "job_transition_conflict"
    return False


def call_with_conflict_handling(
    *,
    logger: Any,
    job_id: UUID,
    log_event: str,
    api_call: Callable[[], object],
) -> None:
    try:
        response = api_call()
    except Exception as exc:  # noqa: BLE001
        if is_conflict_exception(exc):
            logger.warning(log_event, job_id=str(job_id))
            return
        raise

    raise_if_validation_error(response)
    if is_conflict_response(response):
        logger.warning(log_event, job_id=str(job_id))
