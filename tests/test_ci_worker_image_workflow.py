from __future__ import annotations

from pathlib import Path


def test_ci_publishes_both_named_worker_profiles_and_legacy_atom_alias() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "build-worker-images:" in workflow
    assert "build-worker-sifs:" in workflow
    assert "key: atom-openmm" in workflow
    assert "key: gcncmcmd" in workflow
    assert "Dockerfile.worker-${{ matrix.key }}-base" in workflow
    assert "Dockerfile.worker" in workflow
    assert "relaymd-worker-${PROFILE}:sif-sha-${short_sha}" in workflow
    assert "relaymd-worker:sha-${short_sha}" in workflow


def test_ci_release_manifest_requires_complete_worker_image_map() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "needs.build-worker-images.result" in workflow
    assert "needs.build-worker-sifs.result" in workflow
    assert (
        "Release manifest requires complete atom-openmm and gcncmcmd worker artifacts." in workflow
    )
    assert (
        '"atom-openmm": {image_uri: $worker_atom_image, sif_uri: $worker_atom_sif_uri}' in workflow
    )
    assert "gcncmcmd: {image_uri: $worker_gcn_image, sif_uri: $worker_gcn_sif_uri}" in workflow
