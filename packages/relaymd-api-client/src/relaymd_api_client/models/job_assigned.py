from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="JobAssigned")


@_attrs_define
class JobAssigned:
    """
    Attributes:
        job_id (UUID):
        input_bundle_path (str):
        latest_checkpoint_path (None | str):
        status (Literal['assigned'] | Unset):  Default: 'assigned'.
    """

    job_id: UUID
    input_bundle_path: str
    latest_checkpoint_path: None | str
    status: Literal["assigned"] | Unset = "assigned"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        job_id = str(self.job_id)

        input_bundle_path = self.input_bundle_path

        latest_checkpoint_path: None | str
        latest_checkpoint_path = self.latest_checkpoint_path

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
                "input_bundle_path": input_bundle_path,
                "latest_checkpoint_path": latest_checkpoint_path,
            }
        )
        if status is not UNSET:
            field_dict["status"] = status

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        input_bundle_path = d.pop("input_bundle_path")

        def _parse_latest_checkpoint_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        latest_checkpoint_path = _parse_latest_checkpoint_path(d.pop("latest_checkpoint_path"))

        status = cast(Literal["assigned"] | Unset, d.pop("status", UNSET))
        if status != "assigned" and not isinstance(status, Unset):
            raise ValueError(f"status must match const 'assigned', got '{status}'")

        job_assigned = cls(
            job_id=job_id,
            input_bundle_path=input_bundle_path,
            latest_checkpoint_path=latest_checkpoint_path,
            status=status,
        )

        job_assigned.additional_properties = d
        return job_assigned

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
