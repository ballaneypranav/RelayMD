from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, BinaryIO, TextIO, TYPE_CHECKING, Generator

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

from typing import cast

if TYPE_CHECKING:
  from ..models.worker_image_profile_read import WorkerImageProfileRead





T = TypeVar("T", bound="WorkerImageCatalogRead")



@_attrs_define
class WorkerImageCatalogRead:
    """ 
        Attributes:
            default_worker_image (str):
            worker_images (list[WorkerImageProfileRead]):
     """

    default_worker_image: str
    worker_images: list[WorkerImageProfileRead]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)





    def to_dict(self) -> dict[str, Any]:
        from ..models.worker_image_profile_read import WorkerImageProfileRead
        default_worker_image = self.default_worker_image

        worker_images = []
        for worker_images_item_data in self.worker_images:
            worker_images_item = worker_images_item_data.to_dict()
            worker_images.append(worker_images_item)




        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({
            "default_worker_image": default_worker_image,
            "worker_images": worker_images,
        })

        return field_dict



    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.worker_image_profile_read import WorkerImageProfileRead
        d = dict(src_dict)
        default_worker_image = d.pop("default_worker_image")

        worker_images = []
        _worker_images = d.pop("worker_images")
        for worker_images_item_data in (_worker_images):
            worker_images_item = WorkerImageProfileRead.from_dict(worker_images_item_data)



            worker_images.append(worker_images_item)


        worker_image_catalog_read = cls(
            default_worker_image=default_worker_image,
            worker_images=worker_images,
        )


        worker_image_catalog_read.additional_properties = d
        return worker_image_catalog_read

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
