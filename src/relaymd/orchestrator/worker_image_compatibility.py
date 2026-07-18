from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from relaymd.orchestrator.config import ClusterConfig


@dataclass(frozen=True)
class WorkerImageAvailability:
    clusters: Iterable[ClusterConfig]
    enabled_map: dict[str, bool]
    salad_worker_image_key: str | None = None
    salad_enabled: bool = False


def queue_blocked_reason(
    *,
    preferred_clusters: list[str],
    worker_image_key: str,
    availability: WorkerImageAvailability,
) -> str | None:  # noqa: PLR0911
    """Return the reason a queued job has no currently eligible worker source."""
    all_clusters = list(availability.clusters)
    cluster_by_name = {cluster.name: cluster for cluster in all_clusters}
    if preferred_clusters:
        selected = [cluster_by_name[name] for name in preferred_clusters if name in cluster_by_name]
        if not selected:
            reason = "no_matching_pinned_clusters"
        else:
            enabled = [
                cluster for cluster in selected if availability.enabled_map.get(cluster.name, True)
            ]
            if not enabled:
                reason = "no_enabled_pinned_clusters"
            elif not any(worker_image_key in cluster.worker_images for cluster in enabled):
                reason = "no_compatible_pinned_worker_image_clusters"
            else:
                reason = None
    elif any(
        availability.enabled_map.get(cluster.name, True)
        and worker_image_key in cluster.worker_images
        for cluster in all_clusters
    ) or (availability.salad_enabled and availability.salad_worker_image_key == worker_image_key):
        reason = None
    elif any(worker_image_key in cluster.worker_images for cluster in all_clusters):
        reason = "no_enabled_worker_image_clusters"
    else:
        reason = "no_compatible_worker_image_clusters"
    return reason
