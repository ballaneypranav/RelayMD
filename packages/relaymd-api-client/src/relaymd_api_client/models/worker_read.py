from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.platform import Platform

T = TypeVar("T", bound="WorkerRead")


@_attrs_define
class WorkerRead:
    """
    Attributes:
        id (UUID):
        platform (Platform):
        gpu_model (str):
        gpu_count (int):
        vram_gb (int):
        last_heartbeat (datetime.datetime):
    """

    id: UUID
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    last_heartbeat: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        platform = self.platform.value

        gpu_model = self.gpu_model

        gpu_count = self.gpu_count

        vram_gb = self.vram_gb

        last_heartbeat = self.last_heartbeat.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "platform": platform,
                "gpu_model": gpu_model,
                "gpu_count": gpu_count,
                "vram_gb": vram_gb,
                "last_heartbeat": last_heartbeat,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        platform = Platform(d.pop("platform"))

        gpu_model = d.pop("gpu_model")

        gpu_count = d.pop("gpu_count")

        vram_gb = d.pop("vram_gb")

        last_heartbeat = isoparse(d.pop("last_heartbeat"))

        worker_read = cls(
            id=id,
            platform=platform,
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            vram_gb=vram_gb,
            last_heartbeat=last_heartbeat,
        )

        worker_read.additional_properties = d
        return worker_read

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
