from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.platform import Platform
from ..models.worker_status import WorkerStatus
from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
from uuid import UUID
import datetime






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
            status (WorkerStatus):
            worker_image_key (str):
            last_heartbeat (datetime.datetime):
            registered_at (datetime.datetime):
            provider_id (None | str | Unset):
            provider_state (None | str | Unset):
            provider_state_raw (None | str | Unset):
            provider_reason (None | str | Unset):
            provider_last_checked_at (datetime.datetime | None | Unset):
     """

    id: UUID
    platform: Platform
    gpu_model: str
    gpu_count: int
    vram_gb: int
    status: WorkerStatus
    worker_image_key: str
    last_heartbeat: datetime.datetime
    registered_at: datetime.datetime
    provider_id: None | str | Unset = UNSET
    provider_state: None | str | Unset = UNSET
    provider_state_raw: None | str | Unset = UNSET
    provider_reason: None | str | Unset = UNSET
    provider_last_checked_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        platform = self.platform.value

        gpu_model = self.gpu_model

        gpu_count = self.gpu_count

        vram_gb = self.vram_gb

        status = self.status.value

        worker_image_key = self.worker_image_key

        last_heartbeat = self.last_heartbeat.isoformat()

        registered_at = self.registered_at.isoformat()

        provider_id: None | str | Unset
        if isinstance(self.provider_id, Unset):
            provider_id = UNSET
        else:
            provider_id = self.provider_id

        provider_state: None | str | Unset
        if isinstance(self.provider_state, Unset):
            provider_state = UNSET
        else:
            provider_state = self.provider_state

        provider_state_raw: None | str | Unset
        if isinstance(self.provider_state_raw, Unset):
            provider_state_raw = UNSET
        else:
            provider_state_raw = self.provider_state_raw

        provider_reason: None | str | Unset
        if isinstance(self.provider_reason, Unset):
            provider_reason = UNSET
        else:
            provider_reason = self.provider_reason

        provider_last_checked_at: None | str | Unset
        if isinstance(self.provider_last_checked_at, Unset):
            provider_last_checked_at = UNSET
        elif isinstance(self.provider_last_checked_at, datetime.datetime):
            provider_last_checked_at = self.provider_last_checked_at.isoformat()
        else:
            provider_last_checked_at = self.provider_last_checked_at


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "platform": platform,
            "gpu_model": gpu_model,
            "gpu_count": gpu_count,
            "vram_gb": vram_gb,
            "status": status,
            "worker_image_key": worker_image_key,
            "last_heartbeat": last_heartbeat,
            "registered_at": registered_at,
        })
        if provider_id is not UNSET:
            field_dict["provider_id"] = provider_id
        if provider_state is not UNSET:
            field_dict["provider_state"] = provider_state
        if provider_state_raw is not UNSET:
            field_dict["provider_state_raw"] = provider_state_raw
        if provider_reason is not UNSET:
            field_dict["provider_reason"] = provider_reason
        if provider_last_checked_at is not UNSET:
            field_dict["provider_last_checked_at"] = provider_last_checked_at

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))




        platform = Platform(d.pop("platform"))




        gpu_model = d.pop("gpu_model")

        gpu_count = d.pop("gpu_count")

        vram_gb = d.pop("vram_gb")

        status = WorkerStatus(d.pop("status"))




        worker_image_key = d.pop("worker_image_key")

        last_heartbeat = isoparse(d.pop("last_heartbeat"))




        registered_at = isoparse(d.pop("registered_at"))




        def _parse_provider_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_id = _parse_provider_id(d.pop("provider_id", UNSET))


        def _parse_provider_state(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_state = _parse_provider_state(d.pop("provider_state", UNSET))


        def _parse_provider_state_raw(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_state_raw = _parse_provider_state_raw(d.pop("provider_state_raw", UNSET))


        def _parse_provider_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        provider_reason = _parse_provider_reason(d.pop("provider_reason", UNSET))


        def _parse_provider_last_checked_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                provider_last_checked_at_type_0 = isoparse(data)



                return provider_last_checked_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        provider_last_checked_at = _parse_provider_last_checked_at(d.pop("provider_last_checked_at", UNSET))


        worker_read = cls(
            id=id,
            platform=platform,
            gpu_model=gpu_model,
            gpu_count=gpu_count,
            vram_gb=vram_gb,
            status=status,
            worker_image_key=worker_image_key,
            last_heartbeat=last_heartbeat,
            registered_at=registered_at,
            provider_id=provider_id,
            provider_state=provider_state,
            provider_state_raw=provider_state_raw,
            provider_reason=provider_reason,
            provider_last_checked_at=provider_last_checked_at,
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
