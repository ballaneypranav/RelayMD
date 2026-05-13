from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkpoint_report_checkpoint_cycle_failures_item import (
        CheckpointReportCheckpointCycleFailuresItem,
    )


T = TypeVar("T", bound="CheckpointReport")


@_attrs_define
class CheckpointReport:
    """
    Attributes:
        checkpoint_manifest_path (None | str | Unset):
        checkpoint_path (None | str | Unset):
        progress (float | None | Unset):
        progress_codes (list[str] | Unset):
        checkpoint_cycle_status (None | str | Unset):
        checkpoint_cycle_failures (list[CheckpointReportCheckpointCycleFailuresItem] | Unset):
    """

    checkpoint_manifest_path: None | str | Unset = UNSET
    checkpoint_path: None | str | Unset = UNSET
    progress: float | None | Unset = UNSET
    progress_codes: list[str] | Unset = UNSET
    checkpoint_cycle_status: None | str | Unset = UNSET
    checkpoint_cycle_failures: list[CheckpointReportCheckpointCycleFailuresItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        checkpoint_manifest_path: None | str | Unset
        if isinstance(self.checkpoint_manifest_path, Unset):
            checkpoint_manifest_path = UNSET
        else:
            checkpoint_manifest_path = self.checkpoint_manifest_path

        checkpoint_path: None | str | Unset
        if isinstance(self.checkpoint_path, Unset):
            checkpoint_path = UNSET
        else:
            checkpoint_path = self.checkpoint_path

        progress: float | None | Unset
        if isinstance(self.progress, Unset):
            progress = UNSET
        else:
            progress = self.progress

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
        field_dict.update({})
        if checkpoint_manifest_path is not UNSET:
            field_dict["checkpoint_manifest_path"] = checkpoint_manifest_path
        if checkpoint_path is not UNSET:
            field_dict["checkpoint_path"] = checkpoint_path
        if progress is not UNSET:
            field_dict["progress"] = progress
        if progress_codes is not UNSET:
            field_dict["progress_codes"] = progress_codes
        if checkpoint_cycle_status is not UNSET:
            field_dict["checkpoint_cycle_status"] = checkpoint_cycle_status
        if checkpoint_cycle_failures is not UNSET:
            field_dict["checkpoint_cycle_failures"] = checkpoint_cycle_failures

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkpoint_report_checkpoint_cycle_failures_item import (
            CheckpointReportCheckpointCycleFailuresItem,
        )

        d = dict(src_dict)

        def _parse_checkpoint_manifest_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        checkpoint_manifest_path = _parse_checkpoint_manifest_path(
            d.pop("checkpoint_manifest_path", UNSET)
        )

        def _parse_checkpoint_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        checkpoint_path = _parse_checkpoint_path(d.pop("checkpoint_path", UNSET))

        def _parse_progress(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        progress = _parse_progress(d.pop("progress", UNSET))

        progress_codes = cast(list[str], d.pop("progress_codes", UNSET))

        def _parse_checkpoint_cycle_status(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        checkpoint_cycle_status = _parse_checkpoint_cycle_status(
            d.pop("checkpoint_cycle_status", UNSET)
        )

        _checkpoint_cycle_failures = d.pop("checkpoint_cycle_failures", UNSET)
        checkpoint_cycle_failures: list[CheckpointReportCheckpointCycleFailuresItem] | Unset = UNSET
        if _checkpoint_cycle_failures is not UNSET:
            checkpoint_cycle_failures = []
            for checkpoint_cycle_failures_item_data in _checkpoint_cycle_failures:
                checkpoint_cycle_failures_item = (
                    CheckpointReportCheckpointCycleFailuresItem.from_dict(
                        checkpoint_cycle_failures_item_data
                    )
                )

                checkpoint_cycle_failures.append(checkpoint_cycle_failures_item)

        checkpoint_report = cls(
            checkpoint_manifest_path=checkpoint_manifest_path,
            checkpoint_path=checkpoint_path,
            progress=progress,
            progress_codes=progress_codes,
            checkpoint_cycle_status=checkpoint_cycle_status,
            checkpoint_cycle_failures=checkpoint_cycle_failures,
        )

        checkpoint_report.additional_properties = d
        return checkpoint_report

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
