from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Request, status
from relaymd.orchestrator.config import OrchestratorSettings


def require_worker_api_token(
    request: Request,
    x_api_token: Annotated[str | None, Header(alias="X-API-Token")] = None,
) -> None:
    settings: OrchestratorSettings = request.app.state.settings
    if not x_api_token or x_api_token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
        )
