from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.orchestrator.auth import require_worker_api_token
from relaymd.orchestrator.config import OrchestratorSettings
from relaymd.orchestrator.db import get_session
from relaymd.orchestrator.services.cluster_provisioning_state_service import (
    ClusterProvisioningStateService,
)

router = APIRouter(prefix="/config", dependencies=[Depends(require_worker_api_token)])


class ClusterConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    partition: str
    strategy: str
    max_pending_jobs: int
    wall_time: str
    enabled: bool


class ClusterEnabledMapUpdate(BaseModel):
    enabled: dict[str, bool]


class WorkerImageProfileRead(BaseModel):
    key: str
    display_name: str


class WorkerImageCatalogRead(BaseModel):
    default_worker_image: str
    worker_images: list[WorkerImageProfileRead]


@router.get("/worker-images", response_model=WorkerImageCatalogRead)
async def get_worker_images(request: Request) -> WorkerImageCatalogRead:
    """Return the operator-configured worker image compatibility profiles."""
    settings: OrchestratorSettings = request.app.state.settings
    return WorkerImageCatalogRead(
        default_worker_image=settings.default_worker_image,
        worker_images=[
            WorkerImageProfileRead(key=key, display_name=profile.display_name)
            for key, profile in sorted(settings.worker_image_profiles.items())
        ],
    )


@router.get("/slurm-clusters")
async def get_slurm_clusters(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, list[ClusterConfigRead]]:
    settings: OrchestratorSettings = request.app.state.settings
    service = ClusterProvisioningStateService(session)
    enabled_map = await service.get_enabled_map(settings.slurm_cluster_configs)
    clusters = [
        ClusterConfigRead.model_validate(
            {
                "name": cluster.name,
                "partition": cluster.partition,
                "strategy": cluster.strategy,
                "max_pending_jobs": cluster.max_pending_jobs,
                "wall_time": cluster.wall_time,
                "enabled": enabled_map.get(cluster.name, True),
            }
        )
        for cluster in settings.slurm_cluster_configs
    ]
    return {"clusters": clusters}


@router.put("/slurm-clusters/enabled", status_code=status.HTTP_204_NO_CONTENT)
async def update_slurm_cluster_enabled_map(
    request: Request,
    payload: ClusterEnabledMapUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    settings: OrchestratorSettings = request.app.state.settings
    configured_names = {cluster.name for cluster in settings.slurm_cluster_configs}
    payload_names = set(payload.enabled.keys())
    unknown = sorted(payload_names - configured_names)
    missing = sorted(configured_names - payload_names)
    if unknown or missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"unknown_cluster_names": unknown, "missing_cluster_names": missing},
        )

    service = ClusterProvisioningStateService(session)
    await service.replace_enabled_map(payload.enabled)
