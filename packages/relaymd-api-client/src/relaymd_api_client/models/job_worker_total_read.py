from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID






T = TypeVar("T", bound="JobWorkerTotalRead")



@_attrs_define
class JobWorkerTotalRead:
    """ 
        Attributes:
            total_runtime_seconds (float):
            segment_count (int):
            worker_id (None | Unset | UUID):
     """

    total_runtime_seconds: float
    segment_count: int
    worker_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        total_runtime_seconds = self.total_runtime_seconds

        segment_count = self.segment_count

        worker_id: None | str | Unset
        if isinstance(self.worker_id, Unset):
            worker_id = UNSET
        elif isinstance(self.worker_id, UUID):
            worker_id = str(self.worker_id)
        else:
            worker_id = self.worker_id


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "total_runtime_seconds": total_runtime_seconds,
            "segment_count": segment_count,
        })
        if worker_id is not UNSET:
            field_dict["worker_id"] = worker_id

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        total_runtime_seconds = d.pop("total_runtime_seconds")

        segment_count = d.pop("segment_count")

        def _parse_worker_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                worker_id_type_0 = UUID(data)



                return worker_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        worker_id = _parse_worker_id(d.pop("worker_id", UNSET))


        job_worker_total_read = cls(
            total_runtime_seconds=total_runtime_seconds,
            segment_count=segment_count,
            worker_id=worker_id,
        )


        job_worker_total_read.additional_properties = d
        return job_worker_total_read

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
