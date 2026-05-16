from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.platform import Platform
from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="WorkerRegister")



@_attrs_define
class WorkerRegister:
    """ 
        Attributes:
            platform (Platform):
            gpu_model (str):
            gpu_count (int):
            vram_gb (int):
            provider_id (None | str | Unset):
     """

    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    provider_id: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        platform = self.platform.value

        gpu_model = self.gpu_model

        gpu_count = self.gpu_count

        vram_gb = self.vram_gb

        provider_id: None | str | Unset
        if isinstance(self.provider_id, Unset):
            provider_id = UNSET
        else:
            provider_id = self.provider_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "platform": platform,
            "gpu_model": gpu_model,
            "gpu_count": gpu_count,
            "vram_gb": vram_gb,
        })
        if provider_id is not UNSET:
            field_dict["provider_id"] = provider_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        platform = Platform(d.pop("platform"))




        gpu_model = d.pop("gpu_model")

        gpu_count = d.pop("gpu_count")

        vram_gb = d.pop("vram_gb")

        def _parse_provider_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_id = _parse_provider_id(d.pop("provider_id", UNSET))


        worker_register = cls(
            platform=platform,
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            vram_gb=vram_gb,
            provider_id=provider_id,
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
