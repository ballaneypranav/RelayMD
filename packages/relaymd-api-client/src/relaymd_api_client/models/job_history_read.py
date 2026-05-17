from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast

if TYPE_CHECKING:
  from ..models.job_history_event_read import JobHistoryEventRead
  from ..models.job_worker_segment_read import JobWorkerSegmentRead
  from ..models.job_worker_total_read import JobWorkerTotalRead





T = TypeVar("T", bound="JobHistoryRead")



@_attrs_define
class JobHistoryRead:
    """ 
        Attributes:
            events (list[JobHistoryEventRead]):
            worker_segments (list[JobWorkerSegmentRead]):
            worker_totals (list[JobWorkerTotalRead]):
            derived (bool | Unset):  Default: False.
     """

    events: list[JobHistoryEventRead]
    worker_segments: list[JobWorkerSegmentRead]
    worker_totals: list[JobWorkerTotalRead]
    derived: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.job_history_event_read import JobHistoryEventRead
        from ..models.job_worker_total_read import JobWorkerTotalRead
        from ..models.job_worker_segment_read import JobWorkerSegmentRead
        events = []
        for events_item_data in self.events:
            events_item = events_item_data.to_dict()
            events.append(events_item)



        worker_segments = []
        for worker_segments_item_data in self.worker_segments:
            worker_segments_item = worker_segments_item_data.to_dict()
            worker_segments.append(worker_segments_item)



        worker_totals = []
        for worker_totals_item_data in self.worker_totals:
            worker_totals_item = worker_totals_item_data.to_dict()
            worker_totals.append(worker_totals_item)



        derived = self.derived


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "events": events,
            "worker_segments": worker_segments,
            "worker_totals": worker_totals,
        })
        if derived is not UNSET:
            field_dict["derived"] = derived

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_history_event_read import JobHistoryEventRead
        from ..models.job_worker_segment_read import JobWorkerSegmentRead
        from ..models.job_worker_total_read import JobWorkerTotalRead
        d = dict(src_dict)
        events = []
        _events = d.pop("events")
        for events_item_data in (_events):
            events_item = JobHistoryEventRead.from_dict(events_item_data)



            events.append(events_item)


        worker_segments = []
        _worker_segments = d.pop("worker_segments")
        for worker_segments_item_data in (_worker_segments):
            worker_segments_item = JobWorkerSegmentRead.from_dict(worker_segments_item_data)



            worker_segments.append(worker_segments_item)


        worker_totals = []
        _worker_totals = d.pop("worker_totals")
        for worker_totals_item_data in (_worker_totals):
            worker_totals_item = JobWorkerTotalRead.from_dict(worker_totals_item_data)



            worker_totals.append(worker_totals_item)


        derived = d.pop("derived", UNSET)

        job_history_read = cls(
            events=events,
            worker_segments=worker_segments,
            worker_totals=worker_totals,
            derived=derived,
        )


        job_history_read.additional_properties = d
        return job_history_read

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
