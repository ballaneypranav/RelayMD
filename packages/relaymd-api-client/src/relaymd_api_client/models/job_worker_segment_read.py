from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="JobWorkerSegmentRead")


@_attrs_define
class JobWorkerSegmentRead:
    """
    Attributes:
        started_at (datetime.datetime):
        ended_at (datetime.datetime):
        duration_seconds (float):
        worker_id (None | Unset | UUID):
        open_ (bool | Unset):  Default: False.
    """

    started_at: datetime.datetime
    ended_at: datetime.datetime
    duration_seconds: float
    worker_id: None | Unset | UUID = UNSET
    open_: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        started_at = self.started_at.isoformat()

        ended_at = self.ended_at.isoformat()

        duration_seconds = self.duration_seconds

        worker_id: None | str | Unset
        if isinstance(self.worker_id, Unset):
            worker_id = UNSET
        elif isinstance(self.worker_id, UUID):
            worker_id = str(self.worker_id)
        else:
            worker_id = self.worker_id

        open_ = self.open_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_seconds": duration_seconds,
            }
        )
        if worker_id is not UNSET:
            field_dict["worker_id"] = worker_id
        if open_ is not UNSET:
            field_dict["open"] = open_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        started_at = isoparse(d.pop("started_at"))

        ended_at = isoparse(d.pop("ended_at"))

        duration_seconds = d.pop("duration_seconds")

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

        open_ = d.pop("open", UNSET)

        job_worker_segment_read = cls(
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            worker_id=worker_id,
            open_=open_,
        )

        job_worker_segment_read.additional_properties = d
        return job_worker_segment_read

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
