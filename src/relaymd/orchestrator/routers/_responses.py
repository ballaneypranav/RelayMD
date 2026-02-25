from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse

from relaymd.orchestrator.services import JobTransitionConflictError


def job_transition_conflict_response(exc: JobTransitionConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=exc.to_response_model().model_dump(mode="json"),
    )
