from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from ..types import UNSET, Unset
from typing import cast
from uuid import UUID






T = TypeVar("T", bound="JobCreate")



@_attrs_define
class JobCreate:
    """ 
        Attributes:
            title (str):
            input_bundle_path (str):
            id (None | Unset | UUID):
            worker_image_key (None | str | Unset):
            preferred_clusters (list[str] | Unset):
            comment (None | str | Unset):
     """

    title: str
    input_bundle_path: str
    id: None | Unset | UUID = UNSET
    worker_image_key: None | str | Unset = UNSET
    preferred_clusters: list[str] | Unset = UNSET
    comment: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        title = self.title

        input_bundle_path = self.input_bundle_path

        id: None | str | Unset
        if isinstance(self.id, Unset):
            id = UNSET
        elif isinstance(self.id, UUID):
            id = str(self.id)
        else:
            id = self.id

        worker_image_key: None | str | Unset
        if isinstance(self.worker_image_key, Unset):
            worker_image_key = UNSET
        else:
            worker_image_key = self.worker_image_key

        preferred_clusters: list[str] | Unset = UNSET
        if not isinstance(self.preferred_clusters, Unset):
            preferred_clusters = self.preferred_clusters



        comment: None | str | Unset
        if isinstance(self.comment, Unset):
            comment = UNSET
        else:
            comment = self.comment


        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "title": title,
            "input_bundle_path": input_bundle_path,
        })
        if id is not UNSET:
            field_dict["id"] = id
        if worker_image_key is not UNSET:
            field_dict["worker_image_key"] = worker_image_key
        if preferred_clusters is not UNSET:
            field_dict["preferred_clusters"] = preferred_clusters
        if comment is not UNSET:
            field_dict["comment"] = comment

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        title = d.pop("title")

        input_bundle_path = d.pop("input_bundle_path")

        def _parse_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                id_type_0 = UUID(data)



                return id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        id = _parse_id(d.pop("id", UNSET))


        def _parse_worker_image_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        worker_image_key = _parse_worker_image_key(d.pop("worker_image_key", UNSET))


        preferred_clusters = cast(list[str], d.pop("preferred_clusters", UNSET))


        def _parse_comment(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        comment = _parse_comment(d.pop("comment", UNSET))


        job_create = cls(
            title=title,
            input_bundle_path=input_bundle_path,
            id=id,
            worker_image_key=worker_image_key,
            preferred_clusters=preferred_clusters,
            comment=comment,
        )


        job_create.additional_properties = d
        return job_create

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
