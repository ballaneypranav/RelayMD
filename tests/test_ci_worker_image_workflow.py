from __future__ import annotations

from pathlib import Path


def _ci_workflow() -> str:
    return (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )


def test_ci_publishes_only_both_named_worker_profiles() -> None:
    workflow = _ci_workflow()

    assert "build-worker-images:" in workflow
    assert "build-worker-sifs:" in workflow
    assert "key: atom-openmm" in workflow
    assert "key: gcncmcmd" in workflow
    assert "Dockerfile.worker-${{ matrix.key }}-base" in workflow
    assert "Dockerfile.worker" in workflow
    assert "relaymd-worker-${PROFILE}:sif-sha-${short_sha}" in workflow
    assert "Publish AToM compatibility aliases" not in workflow
    assert '"oras://ghcr.io/${OWNER}/relaymd-worker:sif-sha-${short_sha}"' not in workflow


def test_ci_removes_legacy_singular_worker_jobs_and_artifacts() -> None:
    workflow = _ci_workflow()

    for legacy_job in (
        "build-worker-base:",
        "build-worker:",
        "build-worker-base-sif:",
        "build-worker-sif:",
    ):
        assert f"  {legacy_job}" not in workflow

    for legacy_reference in (
        "Dockerfile.worker-base",
        "relaymd-worker-base",
        "relaymd-worker:sha-",
        "relaymd-worker:sif-",
        "relaymd-worker.sif",
        "relaymd-worker.localdev.def",
    ):
        assert legacy_reference not in workflow


def test_ci_release_manifest_requires_complete_worker_image_map() -> None:
    workflow = _ci_workflow()

    assert "needs.build-worker-images.result" in workflow
    assert "needs.build-worker-sifs.result" in workflow
    assert (
        "Release manifest requires complete atom-openmm and gcncmcmd worker artifacts." in workflow
    )
    assert (
        '"atom-openmm": {image_uri: $worker_atom_image, sif_uri: $worker_atom_sif_uri}' in workflow
    )
    assert "gcncmcmd: {image_uri: $worker_gcn_image, sif_uri: $worker_gcn_sif_uri}" in workflow
