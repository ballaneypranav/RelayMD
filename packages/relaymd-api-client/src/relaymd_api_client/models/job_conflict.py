from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.job_status import JobStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="JobConflict")


@_attrs_define
class JobConflict:
    """
    Attributes:
        message (str):
        error (Literal['job_transition_conflict'] | Unset):  Default: 'job_transition_conflict'.
        job_id (None | Unset | UUID):
        current_status (JobStatus | None | Unset):
        requested_status (JobStatus | None | Unset):
    """

    message: str
    error: Literal["job_transition_conflict"] | Unset = "job_transition_conflict"
    job_id: None | Unset | UUID = UNSET
    current_status: JobStatus | None | Unset = UNSET
    requested_status: JobStatus | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message = self.message

        error = self.error

        job_id: None | str | Unset
        if isinstance(self.job_id, Unset):
            job_id = UNSET
        elif isinstance(self.job_id, UUID):
            job_id = str(self.job_id)
        else:
            job_id = self.job_id

        current_status: None | str | Unset
        if isinstance(self.current_status, Unset):
            current_status = UNSET
        elif isinstance(self.current_status, JobStatus):
            current_status = self.current_status.value
        else:
            current_status = self.current_status

        requested_status: None | str | Unset
        if isinstance(self.requested_status, Unset):
            requested_status = UNSET
        elif isinstance(self.requested_status, JobStatus):
            requested_status = self.requested_status.value
        else:
            requested_status = self.requested_status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message": message,
            }
        )
        if error is not UNSET:
            field_dict["error"] = error
        if job_id is not UNSET:
            field_dict["job_id"] = job_id
        if current_status is not UNSET:
            field_dict["current_status"] = current_status
        if requested_status is not UNSET:
            field_dict["requested_status"] = requested_status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message = d.pop("message")

        error = cast(Literal["job_transition_conflict"] | Unset, d.pop("error", UNSET))
        if error != "job_transition_conflict" and not isinstance(error, Unset):
            raise ValueError(f"error must match const 'job_transition_conflict', got '{error}'")

        def _parse_job_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                job_id_type_0 = UUID(data)

                return job_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        job_id = _parse_job_id(d.pop("job_id", UNSET))

        def _parse_current_status(data: object) -> JobStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                current_status_type_0 = JobStatus(data)

                return current_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobStatus | None | Unset, data)

        current_status = _parse_current_status(d.pop("current_status", UNSET))

        def _parse_requested_status(data: object) -> JobStatus | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                requested_status_type_0 = JobStatus(data)

                return requested_status_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobStatus | None | Unset, data)

        requested_status = _parse_requested_status(d.pop("requested_status", UNSET))

        job_conflict = cls(
            message=message,
            error=error,
            job_id=job_id,
            current_status=current_status,
            requested_status=requested_status,
        )

        job_conflict.additional_properties = d
        return job_conflict

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
