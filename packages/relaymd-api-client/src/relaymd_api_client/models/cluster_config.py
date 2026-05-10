from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.cluster_config_idle_strategy_type_0 import ClusterConfigIdleStrategyType0
from ..models.cluster_config_strategy import ClusterConfigStrategy
from ..types import UNSET, Unset

T = TypeVar("T", bound="ClusterConfig")


@_attrs_define
class ClusterConfig:
    """
    Attributes:
        name (str):
        partition (str):
        account (str):
        ssh_host (str):
        ssh_username (str):
        extends (None | str | Unset):
        is_template (bool | Unset):  Default: False.
        ssh_key_file (None | str | Unset):
        ssh_port (int | Unset):  Default: 22.
        gpu_type (str | Unset):  Default: 'unknown'.
        gpu_count (int | Unset):  Default: 0.
        strategy (ClusterConfigStrategy | Unset):  Default: ClusterConfigStrategy.REACTIVE.
        jit_threshold_hours (float | Unset):  Default: 6.0.
        sif_path (None | str | Unset):
        image_uri (None | str | Unset):
        nodes (int | None | Unset):
        ntasks (int | None | Unset):
        qos (None | str | Unset):
        gres (None | str | Unset):
        memory (None | str | Unset):
        memory_per_gpu (None | str | Unset):
        idle_strategy (ClusterConfigIdleStrategyType0 | None | Unset):
        idle_poll_interval_seconds (int | None | Unset):
        idle_poll_max_seconds (int | None | Unset):
        max_pending_jobs (int | Unset):  Default: 1.
        wall_time (str | Unset):  Default: '4:00:00'.
        log_directory (None | str | Unset):
    """

    name: str
    partition: str
    account: str
    ssh_host: str
    ssh_username: str
    extends: None | str | Unset = UNSET
    is_template: bool | Unset = False
    ssh_key_file: None | str | Unset = UNSET
    ssh_port: int | Unset = 22
    gpu_type: str | Unset = "unknown"
    gpu_count: int | Unset = 0
    strategy: ClusterConfigStrategy | Unset = ClusterConfigStrategy.REACTIVE
    jit_threshold_hours: float | Unset = 6.0
    sif_path: None | str | Unset = UNSET
    image_uri: None | str | Unset = UNSET
    nodes: int | None | Unset = UNSET
    ntasks: int | None | Unset = UNSET
    qos: None | str | Unset = UNSET
    gres: None | str | Unset = UNSET
    memory: None | str | Unset = UNSET
    memory_per_gpu: None | str | Unset = UNSET
    idle_strategy: ClusterConfigIdleStrategyType0 | None | Unset = UNSET
    idle_poll_interval_seconds: int | None | Unset = UNSET
    idle_poll_max_seconds: int | None | Unset = UNSET
    max_pending_jobs: int | Unset = 1
    wall_time: str | Unset = "4:00:00"
    log_directory: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        partition = self.partition

        account = self.account

        ssh_host = self.ssh_host

        ssh_username = self.ssh_username

        extends: None | str | Unset
        if isinstance(self.extends, Unset):
            extends = UNSET
        else:
            extends = self.extends

        is_template = self.is_template

        ssh_key_file: None | str | Unset
        if isinstance(self.ssh_key_file, Unset):
            ssh_key_file = UNSET
        else:
            ssh_key_file = self.ssh_key_file

        ssh_port = self.ssh_port

        gpu_type = self.gpu_type

        gpu_count = self.gpu_count

        strategy: str | Unset = UNSET
        if not isinstance(self.strategy, Unset):
            strategy = self.strategy.value

        jit_threshold_hours = self.jit_threshold_hours

        sif_path: None | str | Unset
        if isinstance(self.sif_path, Unset):
            sif_path = UNSET
        else:
            sif_path = self.sif_path

        image_uri: None | str | Unset
        if isinstance(self.image_uri, Unset):
            image_uri = UNSET
        else:
            image_uri = self.image_uri

        nodes: int | None | Unset
        if isinstance(self.nodes, Unset):
            nodes = UNSET
        else:
            nodes = self.nodes

        ntasks: int | None | Unset
        if isinstance(self.ntasks, Unset):
            ntasks = UNSET
        else:
            ntasks = self.ntasks

        qos: None | str | Unset
        if isinstance(self.qos, Unset):
            qos = UNSET
        else:
            qos = self.qos

        gres: None | str | Unset
        if isinstance(self.gres, Unset):
            gres = UNSET
        else:
            gres = self.gres

        memory: None | str | Unset
        if isinstance(self.memory, Unset):
            memory = UNSET
        else:
            memory = self.memory

        memory_per_gpu: None | str | Unset
        if isinstance(self.memory_per_gpu, Unset):
            memory_per_gpu = UNSET
        else:
            memory_per_gpu = self.memory_per_gpu

        idle_strategy: None | str | Unset
        if isinstance(self.idle_strategy, Unset):
            idle_strategy = UNSET
        elif isinstance(self.idle_strategy, ClusterConfigIdleStrategyType0):
            idle_strategy = self.idle_strategy.value
        else:
            idle_strategy = self.idle_strategy

        idle_poll_interval_seconds: int | None | Unset
        if isinstance(self.idle_poll_interval_seconds, Unset):
            idle_poll_interval_seconds = UNSET
        else:
            idle_poll_interval_seconds = self.idle_poll_interval_seconds

        idle_poll_max_seconds: int | None | Unset
        if isinstance(self.idle_poll_max_seconds, Unset):
            idle_poll_max_seconds = UNSET
        else:
            idle_poll_max_seconds = self.idle_poll_max_seconds

        max_pending_jobs = self.max_pending_jobs

        wall_time = self.wall_time

        log_directory: None | str | Unset
        if isinstance(self.log_directory, Unset):
            log_directory = UNSET
        else:
            log_directory = self.log_directory

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "partition": partition,
                "account": account,
                "ssh_host": ssh_host,
                "ssh_username": ssh_username,
            }
        )
        if extends is not UNSET:
            field_dict["extends"] = extends
        if is_template is not UNSET:
            field_dict["is_template"] = is_template
        if ssh_key_file is not UNSET:
            field_dict["ssh_key_file"] = ssh_key_file
        if ssh_port is not UNSET:
            field_dict["ssh_port"] = ssh_port
        if gpu_type is not UNSET:
            field_dict["gpu_type"] = gpu_type
        if gpu_count is not UNSET:
            field_dict["gpu_count"] = gpu_count
        if strategy is not UNSET:
            field_dict["strategy"] = strategy
        if jit_threshold_hours is not UNSET:
            field_dict["jit_threshold_hours"] = jit_threshold_hours
        if sif_path is not UNSET:
            field_dict["sif_path"] = sif_path
        if image_uri is not UNSET:
            field_dict["image_uri"] = image_uri
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if ntasks is not UNSET:
            field_dict["ntasks"] = ntasks
        if qos is not UNSET:
            field_dict["qos"] = qos
        if gres is not UNSET:
            field_dict["gres"] = gres
        if memory is not UNSET:
            field_dict["memory"] = memory
        if memory_per_gpu is not UNSET:
            field_dict["memory_per_gpu"] = memory_per_gpu
        if idle_strategy is not UNSET:
            field_dict["idle_strategy"] = idle_strategy
        if idle_poll_interval_seconds is not UNSET:
            field_dict["idle_poll_interval_seconds"] = idle_poll_interval_seconds
        if idle_poll_max_seconds is not UNSET:
            field_dict["idle_poll_max_seconds"] = idle_poll_max_seconds
        if max_pending_jobs is not UNSET:
            field_dict["max_pending_jobs"] = max_pending_jobs
        if wall_time is not UNSET:
            field_dict["wall_time"] = wall_time
        if log_directory is not UNSET:
            field_dict["log_directory"] = log_directory

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        partition = d.pop("partition")

        account = d.pop("account")

        ssh_host = d.pop("ssh_host")

        ssh_username = d.pop("ssh_username")

        def _parse_extends(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        extends = _parse_extends(d.pop("extends", UNSET))

        is_template = d.pop("is_template", UNSET)

        def _parse_ssh_key_file(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ssh_key_file = _parse_ssh_key_file(d.pop("ssh_key_file", UNSET))

        ssh_port = d.pop("ssh_port", UNSET)

        gpu_type = d.pop("gpu_type", UNSET)

        gpu_count = d.pop("gpu_count", UNSET)

        _strategy = d.pop("strategy", UNSET)
        strategy: ClusterConfigStrategy | Unset
        if isinstance(_strategy, Unset):
            strategy = UNSET
        else:
            strategy = ClusterConfigStrategy(_strategy)

        jit_threshold_hours = d.pop("jit_threshold_hours", UNSET)

        def _parse_sif_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sif_path = _parse_sif_path(d.pop("sif_path", UNSET))

        def _parse_image_uri(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        image_uri = _parse_image_uri(d.pop("image_uri", UNSET))

        def _parse_nodes(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        nodes = _parse_nodes(d.pop("nodes", UNSET))

        def _parse_ntasks(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ntasks = _parse_ntasks(d.pop("ntasks", UNSET))

        def _parse_qos(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        qos = _parse_qos(d.pop("qos", UNSET))

        def _parse_gres(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        gres = _parse_gres(d.pop("gres", UNSET))

        def _parse_memory(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        memory = _parse_memory(d.pop("memory", UNSET))

        def _parse_memory_per_gpu(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        memory_per_gpu = _parse_memory_per_gpu(d.pop("memory_per_gpu", UNSET))

        def _parse_idle_strategy(data: object) -> ClusterConfigIdleStrategyType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                idle_strategy_type_0 = ClusterConfigIdleStrategyType0(data)

                return idle_strategy_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(ClusterConfigIdleStrategyType0 | None | Unset, data)

        idle_strategy = _parse_idle_strategy(d.pop("idle_strategy", UNSET))

        def _parse_idle_poll_interval_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        idle_poll_interval_seconds = _parse_idle_poll_interval_seconds(
            d.pop("idle_poll_interval_seconds", UNSET)
        )

        def _parse_idle_poll_max_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        idle_poll_max_seconds = _parse_idle_poll_max_seconds(d.pop("idle_poll_max_seconds", UNSET))

        max_pending_jobs = d.pop("max_pending_jobs", UNSET)

        wall_time = d.pop("wall_time", UNSET)

        def _parse_log_directory(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        log_directory = _parse_log_directory(d.pop("log_directory", UNSET))

        cluster_config = cls(
            name=name,
            partition=partition,
            account=account,
            ssh_host=ssh_host,
            ssh_username=ssh_username,
            extends=extends,
            is_template=is_template,
            ssh_key_file=ssh_key_file,
            ssh_port=ssh_port,
            gpu_type=gpu_type,
            gpu_count=gpu_count,
            strategy=strategy,
            jit_threshold_hours=jit_threshold_hours,
            sif_path=sif_path,
            image_uri=image_uri,
            nodes=nodes,
            ntasks=ntasks,
            qos=qos,
            gres=gres,
            memory=memory,
            memory_per_gpu=memory_per_gpu,
            idle_strategy=idle_strategy,
            idle_poll_interval_seconds=idle_poll_interval_seconds,
            idle_poll_max_seconds=idle_poll_max_seconds,
            max_pending_jobs=max_pending_jobs,
            wall_time=wall_time,
            log_directory=log_directory,
        )

        cluster_config.additional_properties = d
        return cluster_config

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
