from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings

router = APIRouter(prefix="/config", dependencies=[Depends(require_worker_api_token)])


@router.get("/slurm-clusters")
async def get_slurm_clusters(request: Request) -> dict[str, list[ClusterConfig]]:
    settings: OrchestratorSettings = request.app.state.settings
    return {"clusters": settings.slurm_cluster_configs}
