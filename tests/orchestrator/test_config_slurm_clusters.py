from __future__ import annotations

from typing import Any, cast

import pytest

from relaymd.orchestrator.config import ClusterConfig, OrchestratorSettings, WorkerImageSource


def _worker_images(
    *,
    sif_path: str | None = None,
    image_uri: str | None = None,
    sif_cache_dir: str | None = None,
) -> dict[str, WorkerImageSource]:
    return {
        "atom-openmm": WorkerImageSource(
            sif_path=sif_path,
            image_uri=image_uri,
            sif_cache_dir=sif_cache_dir,
        )
    }


def test_slurm_cluster_partition_must_be_singular_string() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-a30",
                    "partition": "a30",
                    "account": "my-account",
                    "ssh_host": "host1",
                    "ssh_username": "user1",
                    "worker_images": {
                        "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                    },
                }
            ],
        ),
    )

    assert settings.slurm_cluster_configs[0].partition == "a30"


def test_slurm_cluster_partition_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid partition list"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "gilbreth",
                        "partition": ["a30", "a100"],
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    }
                ],
            ),
        )


def test_slurm_cluster_inheritance_child_overrides_parent() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "partition": "a30",
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "qos": "standby",
                    "worker_images": {
                        "atom-openmm": {"sif_path": "/shared/containers/atom-openmm-base.sif"}
                    },
                },
                {
                    "name": "gilbreth-a100",
                    "extends": "gilbreth-template",
                    "partition": "a100-80gb",
                    "account": "override-account",
                    "ssh_host": "override-host",
                },
            ],
        ),
    )

    assert settings.slurm_cluster_configs == [
        ClusterConfig(
            name="gilbreth-a100",
            extends="gilbreth-template",
            is_template=False,
            partition="a100-80gb",
            account="override-account",
            ssh_host="override-host",
            ssh_username="base-user",
            qos="standby",
            worker_images=_worker_images(sif_path="/shared/containers/atom-openmm-base.sif"),
        )
    ]


def test_slurm_cluster_templates_are_excluded_from_runtime_clusters() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "partition": "a30",
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "worker_images": {
                        "atom-openmm": {"sif_path": "/shared/containers/atom-openmm-base.sif"}
                    },
                },
                {
                    "name": "gilbreth-a30",
                    "extends": "gilbreth-template",
                    "partition": "a30",
                },
            ],
        ),
    )

    assert [cluster.name for cluster in settings.slurm_cluster_configs] == ["gilbreth-a30"]


def test_slurm_cluster_intermediate_templates_are_excluded_from_runtime_clusters() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        slurm_cluster_configs=cast(
            Any,
            [
                {
                    "name": "gilbreth-template",
                    "is_template": True,
                    "account": "base-account",
                    "ssh_host": "base-host",
                    "ssh_username": "base-user",
                    "worker_images": {
                        "atom-openmm": {"sif_path": "/shared/containers/atom-openmm-base.sif"}
                    },
                },
                {
                    "name": "gilbreth-standby-template",
                    "is_template": True,
                    "extends": "gilbreth-template",
                    "qos": "standby",
                },
                {
                    "name": "gilbreth-standby-a30",
                    "extends": "gilbreth-standby-template",
                    "partition": "a30",
                },
            ],
        ),
    )

    assert [cluster.name for cluster in settings.slurm_cluster_configs] == ["gilbreth-standby-a30"]
    assert settings.slurm_cluster_configs[0].qos == "standby"


def test_slurm_cluster_inheritance_unknown_parent_fails_fast() -> None:
    with pytest.raises(ValueError, match="extends unknown cluster"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "gilbreth-a30",
                        "extends": "missing-template",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    }
                ],
            ),
        )


def test_slurm_cluster_inheritance_cycle_fails_fast() -> None:
    with pytest.raises(ValueError, match="cycle detected"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "cluster-a",
                        "extends": "cluster-b",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    },
                    {
                        "name": "cluster-b",
                        "extends": "cluster-a",
                        "partition": "a100",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    },
                ],
            ),
        )


def test_slurm_cluster_duplicate_names_fail_fast() -> None:
    with pytest.raises(ValueError, match="duplicate slurm cluster config name"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=cast(
                Any,
                [
                    {
                        "name": "cluster-a",
                        "partition": "a30",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    },
                    {
                        "name": "cluster-a",
                        "partition": "a100",
                        "account": "my-account",
                        "ssh_host": "host1",
                        "ssh_username": "user1",
                        "worker_images": {
                            "atom-openmm": {"sif_path": "/shared/containers/atom-openmm.sif"}
                        },
                    },
                ],
            ),
        )
