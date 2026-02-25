from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.platform import Platform

T = TypeVar("T", bound="WorkerRegister")


@_attrs_define
class WorkerRegister:
    """
    Attributes:
        platform (Platform):
        gpu_model (str):
        gpu_count (int):
        vram_gb (int):
    """

    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        platform = self.platform.value

        gpu_model = self.gpu_model

        gpu_count = self.gpu_count

        vram_gb = self.vram_gb

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "platform": platform,
                "gpu_model": gpu_model,
                "gpu_count": gpu_count,
                "vram_gb": vram_gb,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        platform = Platform(d.pop("platform"))

        gpu_model = d.pop("gpu_model")

        gpu_count = d.pop("gpu_count")

        vram_gb = d.pop("vram_gb")

        worker_register = cls(
            platform=platform,
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            vram_gb=vram_gb,
        )

        worker_register.additional_properties = d
        return worker_register

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
