from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from relaymd.models import ClusterProvisioningState
from relaymd.orchestrator.config import ClusterConfig


class ClusterProvisioningStateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_enabled_map(self, clusters: list[ClusterConfig]) -> dict[str, bool]:
        configured_names = [cluster.name for cluster in clusters]
        if not configured_names:
            return {}
        rows = (
            await self._session.exec(
                select(ClusterProvisioningState).where(
                    col(ClusterProvisioningState.cluster_name).in_(configured_names)
                )
            )
        ).all()
        by_name = {row.cluster_name: row for row in rows}
        return {
            name: by_name[name].enabled if name in by_name else True for name in configured_names
        }

    async def replace_enabled_map(self, enabled_map: dict[str, bool]) -> None:
        if not enabled_map:
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        rows = (
            await self._session.exec(
                select(ClusterProvisioningState).where(
                    col(ClusterProvisioningState.cluster_name).in_(list(enabled_map.keys()))
                )
            )
        ).all()
        existing = {row.cluster_name: row for row in rows}
        for cluster_name, enabled in enabled_map.items():
            row = existing.get(cluster_name)
            if row is None:
                row = ClusterProvisioningState(
                    cluster_name=cluster_name,
                    enabled=enabled,
                    updated_at=now,
                )
            else:
                row.enabled = enabled
                row.updated_at = now
            self._session.add(row)
        await self._session.commit()
