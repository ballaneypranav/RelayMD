from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast






T = TypeVar("T", bound="HandoffStart")



@_attrs_define
class HandoffStart:
    """ 
        Attributes:
            reason (str):
            progress (float | None | Unset):
            progress_codes (list[str] | Unset):
            deadline_epoch_seconds (float | None | Unset):
            message (None | str | Unset):
     """

    reason: str
    progress: float | None | Unset = UNSET
    progress_codes: list[str] | Unset = UNSET
    deadline_epoch_seconds: float | None | Unset = UNSET
    message: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        reason = self.reason

        progress: float | None | Unset
        if isinstance(self.progress, Unset):
            progress = UNSET
        else:
            progress = self.progress

        progress_codes: list[str] | Unset = UNSET
        if not isinstance(self.progress_codes, Unset):
            progress_codes = self.progress_codes



        deadline_epoch_seconds: float | None | Unset
        if isinstance(self.deadline_epoch_seconds, Unset):
            deadline_epoch_seconds = UNSET
        else:
            deadline_epoch_seconds = self.deadline_epoch_seconds

        message: None | str | Unset
        if isinstance(self.message, Unset):
            message = UNSET
        else:
            message = self.message


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "reason": reason,
        })
        if progress is not UNSET:
            field_dict["progress"] = progress
        if progress_codes is not UNSET:
            field_dict["progress_codes"] = progress_codes
        if deadline_epoch_seconds is not UNSET:
            field_dict["deadline_epoch_seconds"] = deadline_epoch_seconds
        if message is not UNSET:
            field_dict["message"] = message

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        reason = d.pop("reason")

        def _parse_progress(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        progress = _parse_progress(d.pop("progress", UNSET))


        progress_codes = cast(list[str], d.pop("progress_codes", UNSET))


        def _parse_deadline_epoch_seconds(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        deadline_epoch_seconds = _parse_deadline_epoch_seconds(d.pop("deadline_epoch_seconds", UNSET))


        def _parse_message(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        message = _parse_message(d.pop("message", UNSET))


        handoff_start = cls(
            reason=reason,
            progress=progress,
            progress_codes=progress_codes,
            deadline_epoch_seconds=deadline_epoch_seconds,
            message=message,
        )


        handoff_start.additional_properties = d
        return handoff_start

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
