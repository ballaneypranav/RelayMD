from __future__ import annotations

from pathlib import Path


def test_makefile_has_local_dev_targets() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    makefile = (repo_root / "Makefile").read_text()

    for target in (
        "local-build-images",
        "local-build-sif-or-sandbox",
        "local-build-from-def",
        "local-install-cli",
        "local-smoke",
    ):
        assert f"{target}:" in makefile


def test_local_build_from_def_includes_fallback_to_supported_flow() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_build_from_def.sh").read_text()

    assert "apptainer build --fakeroot" in script
    assert "Self-contained .def build failed; using fallback local OCI->Apptainer flow." in script
    assert "scripts/local_build_sif_or_sandbox.sh" in script
    assert "--fallback" in script
    assert "--rebuild-worker-base" in script
    assert "--rebuild-orchestrator-base" in script
    assert "--rebuild-bases" in script
    assert "relaymd-worker-base.localdev.def" in script
    assert "relaymd-orchestrator-base.localdev.def" in script


def test_local_install_cli_uses_dist_binary_and_atomic_replace() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_install_cli.sh").read_text()

    assert 'SOURCE_BIN="${ROOT_DIR}/dist/relaymd"' in script
    assert 'tmp_target="${TARGET}.tmp.$$"' in script
    assert 'mv "${tmp_target}" "${TARGET}"' in script


def test_experimental_definition_files_are_marked_local_only() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    worker_def = (
        repo_root / "deploy" / "hpc" / "apptainer" / "relaymd-worker.localdev.def"
    ).read_text()
    orch_def = (
        repo_root / "deploy" / "hpc" / "apptainer" / "relaymd-orchestrator.localdev.def"
    ).read_text()
    worker_base_def = (
        repo_root / "deploy" / "hpc" / "apptainer" / "relaymd-worker-base.localdev.def"
    ).read_text()
    orch_base_def = (
        repo_root / "deploy" / "hpc" / "apptainer" / "relaymd-orchestrator-base.localdev.def"
    ).read_text()

    assert "Local RelayMD worker base matching Dockerfile.worker-base." in worker_base_def
    assert "nvidia/cuda:12.1.0-runtime-ubuntu22.04" in worker_base_def
    assert "openmm=8.4.0" in worker_base_def
    assert "git+${ATOM_REPO_URL}@${ATOM_REPO_REF}" in worker_base_def
    assert "Local RelayMD orchestrator base matching Dockerfile.orchestrator-base" in orch_base_def
    assert "python:3.11-slim-bookworm" in orch_base_def
    assert "tailscale" in orch_base_def
    assert "nodejs" in orch_base_def
    assert "Self-contained local RelayMD worker build." in worker_def
    assert "/opt/relaymd/packages/relaymd-worker" in worker_def
    assert "import atom_openmm" in worker_def
    assert "import openmm" in worker_def
    assert "Self-contained local RelayMD orchestrator build." in orch_def
    assert "/opt/relaymd/src" in orch_def
    assert "/opt/relaymd/frontend" in orch_def
    assert "npm run build" in orch_def


def test_local_build_images_supports_engine_selection_and_remediation() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "local_build_images.sh").read_text()

    assert "--engine auto|docker|podman" in script
    assert (
        "Missing local container build engine: neither 'docker' nor 'podman' is available."
        in script
    )
    assert '"${BUILD_ENGINE}" build' in script
