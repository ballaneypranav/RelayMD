from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.job_status import JobStatus

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
        latest_checkpoint_path (None | str):
        last_checkpoint_at (datetime.datetime | None):
        assigned_worker_id (None | UUID):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        preferred_clusters (list[str]):
        comment (None | str):
        queue_blocked_reason (None | str):
    """

    id: UUID
    title: str
    status: JobStatus
    input_bundle_path: str
    assigned_at: datetime.datetime | None
    started_at: datetime.datetime | None
    status_changed_at: datetime.datetime
    latest_checkpoint_path: None | str
    last_checkpoint_at: datetime.datetime | None
    assigned_worker_id: None | UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    preferred_clusters: list[str] = _attrs_field(factory=list)
    comment: None | str = None
    queue_blocked_reason: None | str = None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
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

        latest_checkpoint_path: None | str
        latest_checkpoint_path = self.latest_checkpoint_path

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
        preferred_clusters = self.preferred_clusters
        comment = self.comment
        queue_blocked_reason = self.queue_blocked_reason

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "title": title,
                "status": status,
                "input_bundle_path": input_bundle_path,
                "assigned_at": assigned_at,
                "started_at": started_at,
                "status_changed_at": status_changed_at,
                "latest_checkpoint_path": latest_checkpoint_path,
                "last_checkpoint_at": last_checkpoint_at,
                "assigned_worker_id": assigned_worker_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "preferred_clusters": preferred_clusters,
                "comment": comment,
                "queue_blocked_reason": queue_blocked_reason,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
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

        def _parse_latest_checkpoint_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        latest_checkpoint_path = _parse_latest_checkpoint_path(d.pop("latest_checkpoint_path"))

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
        preferred_clusters = cast(list[str], d.pop("preferred_clusters", []))
        comment = cast(None | str, d.pop("comment", None))
        queue_blocked_reason = cast(None | str, d.pop("queue_blocked_reason", None))

        job_read = cls(
            id=id,
            title=title,
            status=status,
            input_bundle_path=input_bundle_path,
            assigned_at=assigned_at,
            started_at=started_at,
            status_changed_at=status_changed_at,
            latest_checkpoint_path=latest_checkpoint_path,
            last_checkpoint_at=last_checkpoint_at,
            assigned_worker_id=assigned_worker_id,
            created_at=created_at,
            updated_at=updated_at,
            preferred_clusters=preferred_clusters,
            comment=comment,
            queue_blocked_reason=queue_blocked_reason,
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
