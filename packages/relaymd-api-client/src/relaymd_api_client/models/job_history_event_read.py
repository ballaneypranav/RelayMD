from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..models.job_status import JobStatus
from ..types import UNSET, Unset
from dateutil.parser import isoparse
from typing import cast
from uuid import UUID
import datetime

if TYPE_CHECKING:
  from ..models.job_history_event_read_payload import JobHistoryEventReadPayload





T = TypeVar("T", bound="JobHistoryEventRead")



@_attrs_define
class JobHistoryEventRead:
    """ 
        Attributes:
            occurred_at (datetime.datetime):
            event_seq (int):
            event_type (str):
            worker_id (None | Unset | UUID):
            status_from (JobStatus | None | Unset):
            status_to (JobStatus | None | Unset):
            payload (JobHistoryEventReadPayload | Unset):
            derived (bool | Unset):  Default: False.
     """

    occurred_at: datetime.datetime
    event_seq: int
    event_type: str
    worker_id: None | Unset | UUID = UNSET
    status_from: JobStatus | None | Unset = UNSET
    status_to: JobStatus | None | Unset = UNSET
    payload: JobHistoryEventReadPayload | Unset = UNSET
    derived: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.job_history_event_read_payload import JobHistoryEventReadPayload
        occurred_at = self.occurred_at.isoformat()

        event_seq = self.event_seq

        event_type = self.event_type

        worker_id: None | str | Unset
        if isinstance(self.worker_id, Unset):
            worker_id = UNSET
        elif isinstance(self.worker_id, UUID):
            worker_id = str(self.worker_id)
        else:
            worker_id = self.worker_id

        status_from: None | str | Unset
        if isinstance(self.status_from, Unset):
            status_from = UNSET
        elif isinstance(self.status_from, JobStatus):
            status_from = self.status_from.value
        else:
            status_from = self.status_from

        status_to: None | str | Unset
        if isinstance(self.status_to, Unset):
            status_to = UNSET
        elif isinstance(self.status_to, JobStatus):
            status_to = self.status_to.value
        else:
            status_to = self.status_to

        payload: dict[str, Any] | Unset = UNSET
        if not isinstance(self.payload, Unset):
            payload = self.payload.to_dict()

        derived = self.derived


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "occurred_at": occurred_at,
            "event_seq": event_seq,
            "event_type": event_type,
        })
        if worker_id is not UNSET:
            field_dict["worker_id"] = worker_id
        if status_from is not UNSET:
            field_dict["status_from"] = status_from
        if status_to is not UNSET:
            field_dict["status_to"] = status_to
        if payload is not UNSET:
            field_dict["payload"] = payload
        if derived is not UNSET:
            field_dict["derived"] = derived

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_history_event_read_payload import JobHistoryEventReadPayload
        d = dict(src_dict)
        occurred_at = isoparse(d.pop("occurred_at"))




        event_seq = d.pop("event_seq")

        event_type = d.pop("event_type")

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


        def _parse_status_from(data: object) -> JobStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_from_type_0 = JobStatus(data)



                return status_from_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobStatus | None | Unset, data)

        status_from = _parse_status_from(d.pop("status_from", UNSET))


        def _parse_status_to(data: object) -> JobStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                status_to_type_0 = JobStatus(data)



                return status_to_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobStatus | None | Unset, data)

        status_to = _parse_status_to(d.pop("status_to", UNSET))


        _payload = d.pop("payload", UNSET)
        payload: JobHistoryEventReadPayload | Unset
        if isinstance(_payload,  Unset):
            payload = UNSET
        else:
            payload = JobHistoryEventReadPayload.from_dict(_payload)




        derived = d.pop("derived", UNSET)

        job_history_event_read = cls(
            occurred_at=occurred_at,
            event_seq=event_seq,
            event_type=event_type,
            worker_id=worker_id,
            status_from=status_from,
            status_to=status_to,
            payload=payload,
            derived=derived,
        )


        job_history_event_read.additional_properties = d
        return job_history_event_read

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
