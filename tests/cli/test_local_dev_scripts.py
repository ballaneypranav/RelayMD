from __future__ import annotations

from pathlib import Path


def test_makefile_has_local_dev_targets() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    makefile = (repo_root / "Makefile").read_text()

    for target in (
        "local-build-images",
        "local-build-sif-or-sandbox",
        "local-install-cli",
        "local-smoke",
    ):
        assert f"{target}:" in makefile


def test_local_build_sif_or_sandbox_uses_named_worker_profiles() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_build_sif_or_sandbox.sh").read_text()

    assert "--worker-profile atom-openmm|gcncmcmd|all" in script
    assert "relaymd-worker-atom-openmm" in script
    assert "relaymd-worker-gcncmcmd" in script
    assert "relaymd-worker.sif" not in script


def test_local_install_cli_uses_dist_binary_and_atomic_replace() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_install_cli.sh").read_text()

    assert 'SOURCE_BIN="${ROOT_DIR}/dist/relaymd"' in script
    assert 'tmp_target="${TARGET}.tmp.$$"' in script
    assert 'mv "${tmp_target}" "${TARGET}"' in script


def test_legacy_singular_worker_definition_files_are_removed() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert not (repo_root / "Dockerfile.worker-base").exists()
    apptainer_dir = repo_root / "deploy" / "hpc" / "apptainer"
    assert not (apptainer_dir / "relaymd-worker.localdev.def").exists()
    assert not (apptainer_dir / "relaymd-worker-base.localdev.def").exists()


def test_local_build_images_supports_engine_selection_and_remediation() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_build_images.sh").read_text()

    assert "--engine auto|docker|podman" in script
    assert (
        "Missing local container build engine: neither 'docker' nor 'podman' is available."
        in script
    )
    assert '"${BUILD_ENGINE}" build' in script
