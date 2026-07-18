from __future__ import annotations

import pytest

from relaymd.orchestrator.config import (
    ClusterConfig,
    OrchestratorSettings,
    WorkerImageProfile,
    WorkerImageSource,
)


@pytest.fixture(autouse=True)
def _ignore_host_service_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep settings validation tests independent from host configuration."""
    monkeypatch.setenv("RELAYMD_CONFIG", "/tmp/relaymd-test-config-does-not-exist.yaml")


def test_cluster_config_supports_multiple_named_worker_images() -> None:
    cluster = ClusterConfig(
        name="test",
        partition="gpu",
        account="lab",
        ssh_host="test-host",
        ssh_username="test-user",
        worker_images={
            "atom-openmm": WorkerImageSource(sif_path="/shared/atom-openmm.sif"),
            "gcncmcmd": WorkerImageSource(
                image_uri="ghcr.io/acme/relaymd-worker-gcncmcmd:sha-abc1234",
                sif_cache_dir=" /shared/apptainer-cache ",
            ),
        },
    )

    assert cluster.worker_image_source("atom-openmm").apptainer_image == "/shared/atom-openmm.sif"
    assert (
        cluster.worker_image_source("gcncmcmd").apptainer_image
        == "docker://ghcr.io/acme/relaymd-worker-gcncmcmd:sha-abc1234"
    )
    assert cluster.worker_image_source("gcncmcmd").sif_cache_dir == "/shared/apptainer-cache"


def test_legacy_cluster_image_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="cluster-level image fields are unsupported"):
        ClusterConfig.model_validate(
            {
                "name": "test",
                "partition": "gpu",
                "account": "lab",
                "ssh_host": "test-host",
                "ssh_username": "test-user",
                "sif_path": "/shared/atom-openmm.sif",
            }
        )


def test_settings_reject_unknown_cluster_worker_image_key() -> None:
    with pytest.raises(ValueError, match="unknown worker image keys: gcncmcmd"):
        OrchestratorSettings(
            axiom_token="test",
            slurm_cluster_configs=[
                ClusterConfig(
                    name="test",
                    partition="gpu",
                    account="lab",
                    ssh_host="test-host",
                    ssh_username="test-user",
                    worker_images={"gcncmcmd": WorkerImageSource(sif_path="/shared/gcncmcmd.sif")},
                )
            ],
        )


def test_settings_accepts_a_configured_two_image_catalog() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        worker_image_profiles={
            "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
            "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
        },
        slurm_cluster_configs=[
            ClusterConfig(
                name="test",
                partition="gpu",
                account="lab",
                ssh_host="test-host",
                ssh_username="test-user",
                worker_images={
                    "atom-openmm": WorkerImageSource(sif_path="/shared/atom-openmm.sif"),
                    "gcncmcmd": WorkerImageSource(sif_path="/shared/gcncmcmd.sif"),
                },
            )
        ],
    )

    assert settings.default_worker_image == "atom-openmm"
    assert settings.worker_image_profiles["gcncmcmd"].display_name == "GCNCMC-MD"


def test_settings_accepts_default_image_supported_only_by_salad() -> None:
    settings = OrchestratorSettings(
        axiom_token="test",
        worker_image_profiles={
            "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
            "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
        },
        slurm_cluster_configs=[
            ClusterConfig(
                name="gcncmcmd-only",
                partition="gpu",
                account="lab",
                ssh_host="test-host",
                ssh_username="test-user",
                worker_images={"gcncmcmd": WorkerImageSource(sif_path="/shared/gcncmcmd.sif")},
            )
        ],
        salad_api_key="salad-key",
        salad_org="org",
        salad_project="project",
        salad_container_group="group",
    )

    assert settings.salad_autoscaling_enabled is True


def test_settings_rejects_default_image_unsupported_by_salad_only() -> None:
    with pytest.raises(ValueError, match="not supported by any configured compute backend"):
        OrchestratorSettings(
            axiom_token="test",
            worker_image_profiles={
                "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
                "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
            },
            salad_api_key="salad-key",
            salad_org="org",
            salad_project="project",
            salad_container_group="group",
            salad_worker_image_key="gcncmcmd",
        )


def test_salad_worker_image_key_reads_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SALAD_WORKER_IMAGE_KEY", "gcncmcmd")
    settings = OrchestratorSettings(
        axiom_token="test",
        worker_image_profiles={
            "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
            "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
        },
    )

    assert settings.salad_worker_image_key == "gcncmcmd"


def test_cluster_inheritance_merges_worker_images_by_profile() -> None:
    settings = OrchestratorSettings.model_validate(
        {
            "axiom_token": "test",
            "worker_image_profiles": {
                "atom-openmm": WorkerImageProfile(display_name="AToM-OpenMM"),
                "gcncmcmd": WorkerImageProfile(display_name="GCNCMC-MD"),
            },
            "slurm_cluster_configs": [
                {
                    "name": "base",
                    "is_template": True,
                    "partition": "gpu",
                    "account": "lab",
                    "ssh_host": "test-host",
                    "ssh_username": "test-user",
                    "worker_images": {
                        "atom-openmm": {"sif_path": "/shared/atom.sif"},
                        "gcncmcmd": {"sif_path": "/shared/gcn.sif"},
                    },
                },
                {
                    "name": "child",
                    "extends": "base",
                    "worker_images": {"gcncmcmd": {"sif_path": "/override/gcn.sif"}},
                },
            ],
        }
    )

    child = settings.slurm_cluster_configs[0]
    assert child.worker_images["atom-openmm"].sif_path == "/shared/atom.sif"
    assert child.worker_images["gcncmcmd"].sif_path == "/override/gcn.sif"
