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
  from ..models.job_read_checkpoint_cycle_failures_item import JobReadCheckpointCycleFailuresItem





T = TypeVar("T", bound="JobRead")



@_attrs_define
class JobRead:
    """ 
        Attributes:
            id (UUID):
            title (str):
            status (JobStatus):
            input_bundle_path (str):
            assigned_at (datetime.datetime | None):
            started_at (datetime.datetime | None):
            status_changed_at (datetime.datetime):
            latest_checkpoint_manifest_path (None | str):
            last_checkpoint_at (datetime.datetime | None):
            assigned_worker_id (None | UUID):
            created_at (datetime.datetime):
            updated_at (datetime.datetime):
            preferred_clusters (list[str] | Unset):
            comment (None | str | Unset):
            queue_blocked_reason (None | str | Unset):
            cancellation_requested_at (datetime.datetime | None | Unset):
            progress (float | None | Unset):
            runtime_seconds (float | Unset):  Default: 0.0.
            etc_seconds (float | None | Unset):
            ett_seconds (float | None | Unset):
            progress_codes (list[str] | Unset):
            checkpoint_cycle_status (None | str | Unset):
            checkpoint_cycle_failures (list[JobReadCheckpointCycleFailuresItem] | Unset):
     """

    id: UUID
    title: str
    status: JobStatus
    input_bundle_path: str
    assigned_at: datetime.datetime | None
    started_at: datetime.datetime | None
    status_changed_at: datetime.datetime
    latest_checkpoint_manifest_path: None | str
    last_checkpoint_at: datetime.datetime | None
    assigned_worker_id: None | UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    preferred_clusters: list[str] | Unset = UNSET
    comment: None | str | Unset = UNSET
    queue_blocked_reason: None | str | Unset = UNSET
    cancellation_requested_at: datetime.datetime | None | Unset = UNSET
    progress: float | None | Unset = UNSET
    runtime_seconds: float | Unset = 0.0
    etc_seconds: float | None | Unset = UNSET
    ett_seconds: float | None | Unset = UNSET
    progress_codes: list[str] | Unset = UNSET
    checkpoint_cycle_status: None | str | Unset = UNSET
    checkpoint_cycle_failures: list[JobReadCheckpointCycleFailuresItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.job_read_checkpoint_cycle_failures_item import JobReadCheckpointCycleFailuresItem
        id = str(self.id)

        title = self.title

        status = self.status.value

        input_bundle_path = self.input_bundle_path

        assigned_at: None | str
        if isinstance(self.assigned_at, datetime.datetime):
            assigned_at = self.assigned_at.isoformat()
        else:
            assigned_at = self.assigned_at

        started_at: None | str
        if isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        status_changed_at = self.status_changed_at.isoformat()

        latest_checkpoint_manifest_path: None | str
        latest_checkpoint_manifest_path = self.latest_checkpoint_manifest_path

        last_checkpoint_at: None | str
        if isinstance(self.last_checkpoint_at, datetime.datetime):
            last_checkpoint_at = self.last_checkpoint_at.isoformat()
        else:
            last_checkpoint_at = self.last_checkpoint_at

        assigned_worker_id: None | str
        if isinstance(self.assigned_worker_id, UUID):
            assigned_worker_id = str(self.assigned_worker_id)
        else:
            assigned_worker_id = self.assigned_worker_id

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        preferred_clusters: list[str] | Unset = UNSET
        if not isinstance(self.preferred_clusters, Unset):
            preferred_clusters = self.preferred_clusters



        comment: None | str | Unset
        if isinstance(self.comment, Unset):
            comment = UNSET
        else:
            comment = self.comment

        queue_blocked_reason: None | str | Unset
        if isinstance(self.queue_blocked_reason, Unset):
            queue_blocked_reason = UNSET
        else:
            queue_blocked_reason = self.queue_blocked_reason

        cancellation_requested_at: None | str | Unset
        if isinstance(self.cancellation_requested_at, Unset):
            cancellation_requested_at = UNSET
        elif isinstance(self.cancellation_requested_at, datetime.datetime):
            cancellation_requested_at = self.cancellation_requested_at.isoformat()
        else:
            cancellation_requested_at = self.cancellation_requested_at

        progress: float | None | Unset
        if isinstance(self.progress, Unset):
            progress = UNSET
        else:
            progress = self.progress

        runtime_seconds = self.runtime_seconds

        etc_seconds: float | None | Unset
        if isinstance(self.etc_seconds, Unset):
            etc_seconds = UNSET
        else:
            etc_seconds = self.etc_seconds

        ett_seconds: float | None | Unset
        if isinstance(self.ett_seconds, Unset):
            ett_seconds = UNSET
        else:
            ett_seconds = self.ett_seconds

        progress_codes: list[str] | Unset = UNSET
        if not isinstance(self.progress_codes, Unset):
            progress_codes = self.progress_codes



        checkpoint_cycle_status: None | str | Unset
        if isinstance(self.checkpoint_cycle_status, Unset):
            checkpoint_cycle_status = UNSET
        else:
            checkpoint_cycle_status = self.checkpoint_cycle_status

        checkpoint_cycle_failures: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.checkpoint_cycle_failures, Unset):
            checkpoint_cycle_failures = []
            for checkpoint_cycle_failures_item_data in self.checkpoint_cycle_failures:
                checkpoint_cycle_failures_item = checkpoint_cycle_failures_item_data.to_dict()
                checkpoint_cycle_failures.append(checkpoint_cycle_failures_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "id": id,
            "title": title,
            "status": status,
            "input_bundle_path": input_bundle_path,
            "assigned_at": assigned_at,
            "started_at": started_at,
            "status_changed_at": status_changed_at,
            "latest_checkpoint_manifest_path": latest_checkpoint_manifest_path,
            "last_checkpoint_at": last_checkpoint_at,
            "assigned_worker_id": assigned_worker_id,
            "created_at": created_at,
            "updated_at": updated_at,
        })
        if preferred_clusters is not UNSET:
            field_dict["preferred_clusters"] = preferred_clusters
        if comment is not UNSET:
            field_dict["comment"] = comment
        if queue_blocked_reason is not UNSET:
            field_dict["queue_blocked_reason"] = queue_blocked_reason
        if cancellation_requested_at is not UNSET:
            field_dict["cancellation_requested_at"] = cancellation_requested_at
        if progress is not UNSET:
            field_dict["progress"] = progress
        if runtime_seconds is not UNSET:
            field_dict["runtime_seconds"] = runtime_seconds
        if etc_seconds is not UNSET:
            field_dict["etc_seconds"] = etc_seconds
        if ett_seconds is not UNSET:
            field_dict["ett_seconds"] = ett_seconds
        if progress_codes is not UNSET:
            field_dict["progress_codes"] = progress_codes
        if checkpoint_cycle_status is not UNSET:
            field_dict["checkpoint_cycle_status"] = checkpoint_cycle_status
        if checkpoint_cycle_failures is not UNSET:
            field_dict["checkpoint_cycle_failures"] = checkpoint_cycle_failures

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_read_checkpoint_cycle_failures_item import JobReadCheckpointCycleFailuresItem
        d = dict(src_dict)
        id = UUID(d.pop("id"))




        title = d.pop("title")

        status = JobStatus(d.pop("status"))




        input_bundle_path = d.pop("input_bundle_path")

        def _parse_assigned_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                assigned_at_type_0 = isoparse(data)



                return assigned_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        assigned_at = _parse_assigned_at(d.pop("assigned_at"))


        def _parse_started_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = isoparse(data)



                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        started_at = _parse_started_at(d.pop("started_at"))


        status_changed_at = isoparse(d.pop("status_changed_at"))




        def _parse_latest_checkpoint_manifest_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        latest_checkpoint_manifest_path = _parse_latest_checkpoint_manifest_path(d.pop("latest_checkpoint_manifest_path"))


        def _parse_last_checkpoint_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_checkpoint_at_type_0 = isoparse(data)



                return last_checkpoint_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_checkpoint_at = _parse_last_checkpoint_at(d.pop("last_checkpoint_at"))


        def _parse_assigned_worker_id(data: object) -> None | UUID:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                assigned_worker_id_type_0 = UUID(data)



                return assigned_worker_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | UUID, data)

        assigned_worker_id = _parse_assigned_worker_id(d.pop("assigned_worker_id"))


        created_at = isoparse(d.pop("created_at"))




        updated_at = isoparse(d.pop("updated_at"))




        preferred_clusters = cast(list[str], d.pop("preferred_clusters", UNSET))


        def _parse_comment(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        comment = _parse_comment(d.pop("comment", UNSET))


        def _parse_queue_blocked_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        queue_blocked_reason = _parse_queue_blocked_reason(d.pop("queue_blocked_reason", UNSET))


        def _parse_cancellation_requested_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                cancellation_requested_at_type_0 = isoparse(data)



                return cancellation_requested_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        cancellation_requested_at = _parse_cancellation_requested_at(d.pop("cancellation_requested_at", UNSET))


        def _parse_progress(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        progress = _parse_progress(d.pop("progress", UNSET))


        runtime_seconds = d.pop("runtime_seconds", UNSET)

        def _parse_etc_seconds(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        etc_seconds = _parse_etc_seconds(d.pop("etc_seconds", UNSET))


        def _parse_ett_seconds(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        ett_seconds = _parse_ett_seconds(d.pop("ett_seconds", UNSET))


        progress_codes = cast(list[str], d.pop("progress_codes", UNSET))


        def _parse_checkpoint_cycle_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        checkpoint_cycle_status = _parse_checkpoint_cycle_status(d.pop("checkpoint_cycle_status", UNSET))


        _checkpoint_cycle_failures = d.pop("checkpoint_cycle_failures", UNSET)
        checkpoint_cycle_failures: list[JobReadCheckpointCycleFailuresItem] | Unset = UNSET
        if _checkpoint_cycle_failures is not UNSET:
            checkpoint_cycle_failures = []
            for checkpoint_cycle_failures_item_data in _checkpoint_cycle_failures:
                checkpoint_cycle_failures_item = JobReadCheckpointCycleFailuresItem.from_dict(checkpoint_cycle_failures_item_data)



                checkpoint_cycle_failures.append(checkpoint_cycle_failures_item)


        job_read = cls(
            id=id,
            title=title,
            status=status,
            input_bundle_path=input_bundle_path,
            assigned_at=assigned_at,
            started_at=started_at,
            status_changed_at=status_changed_at,
            latest_checkpoint_manifest_path=latest_checkpoint_manifest_path,
            last_checkpoint_at=last_checkpoint_at,
            assigned_worker_id=assigned_worker_id,
            created_at=created_at,
            updated_at=updated_at,
            preferred_clusters=preferred_clusters,
            comment=comment,
            queue_blocked_reason=queue_blocked_reason,
            cancellation_requested_at=cancellation_requested_at,
            progress=progress,
            runtime_seconds=runtime_seconds,
            etc_seconds=etc_seconds,
            ett_seconds=ett_seconds,
            progress_codes=progress_codes,
            checkpoint_cycle_status=checkpoint_cycle_status,
            checkpoint_cycle_failures=checkpoint_cycle_failures,
        )


        job_read.additional_properties = d
        return job_read

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
