from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.cluster_enabled_map_update_enabled import ClusterEnabledMapUpdateEnabled





T = TypeVar("T", bound="ClusterEnabledMapUpdate")



@_attrs_define
class ClusterEnabledMapUpdate:
    """ 
        Attributes:
            enabled (ClusterEnabledMapUpdateEnabled):
     """

    enabled: ClusterEnabledMapUpdateEnabled
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.cluster_enabled_map_update_enabled import ClusterEnabledMapUpdateEnabled
        enabled = self.enabled.to_dict()


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "enabled": enabled,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.cluster_enabled_map_update_enabled import ClusterEnabledMapUpdateEnabled
        d = dict(src_dict)
        enabled = ClusterEnabledMapUpdateEnabled.from_dict(d.pop("enabled"))




        cluster_enabled_map_update = cls(
            enabled=enabled,
        )


        cluster_enabled_map_update.additional_properties = d
        return cluster_enabled_map_update

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
