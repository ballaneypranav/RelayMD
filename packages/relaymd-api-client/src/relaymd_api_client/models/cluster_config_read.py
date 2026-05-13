from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ClusterConfigRead")


@_attrs_define
class ClusterConfigRead:
    """
    Attributes:
        name (str):
        partition (str):
        strategy (str):
        max_pending_jobs (int):
        wall_time (str):
        enabled (bool):
    """

    name: str
    partition: str
    strategy: str
    max_pending_jobs: int
    wall_time: str
    enabled: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        partition = self.partition

        strategy = self.strategy

        max_pending_jobs = self.max_pending_jobs

        wall_time = self.wall_time

        enabled = self.enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "partition": partition,
                "strategy": strategy,
                "max_pending_jobs": max_pending_jobs,
                "wall_time": wall_time,
                "enabled": enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        partition = d.pop("partition")

        strategy = d.pop("strategy")

        max_pending_jobs = d.pop("max_pending_jobs")

        wall_time = d.pop("wall_time")

        enabled = d.pop("enabled")

        cluster_config_read = cls(
            name=name,
            partition=partition,
            strategy=strategy,
            max_pending_jobs=max_pending_jobs,
            wall_time=wall_time,
            enabled=enabled,
        )

        cluster_config_read.additional_properties = d
        return cluster_config_read

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
