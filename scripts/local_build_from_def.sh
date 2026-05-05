#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_from_def.sh [--release <name>] [--current-link <path>] [--service-root <path>]

Experimental/local-only path:
- Attempts apptainer build from .def files with --fakeroot.
- Falls back to local_build_sif_or_sandbox.sh if fakeroot/subuid support is unavailable.
USAGE
}

RELEASE_NAME="${RELEASE_NAME:-local-def-dev}"
RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
CURRENT_LINK="${CURRENT_LINK:-${RELAYMD_SERVICE_ROOT}/current}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        --current-link)
            CURRENT_LINK="$2"
            shift 2
            ;;
        --service-root)
            RELAYMD_SERVICE_ROOT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-worker.localdev.def"
ORCH_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-orchestrator.localdev.def"
RELEASES_DIR="${RELAYMD_SERVICE_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_NAME}"

if ! command -v apptainer >/dev/null 2>&1; then
    echo "Missing required command 'apptainer'." >&2
    exit 1
fi

mkdir -p "${RELEASE_DIR}"

set +e
apptainer build --fakeroot "${RELEASE_DIR}/relaymd-worker.sif" "${WORKER_DEF}"
worker_rc=$?
apptainer build --fakeroot "${RELEASE_DIR}/relaymd-orchestrator.sif" "${ORCH_DEF}"
orch_rc=$?
set -e

if [[ "${worker_rc}" -eq 0 && "${orch_rc}" -eq 0 ]]; then
    ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"
    cat <<OUT
Experimental .def build succeeded.
  release: ${RELEASE_DIR}
  current: ${CURRENT_LINK} -> ${RELEASE_DIR}
OUT
    exit 0
fi

echo "Experimental .def build failed (unsupported fakeroot/subuid is common on HPC)." >&2
echo "Falling back to supported local OCI->Apptainer pull flow." >&2
"${ROOT_DIR}/scripts/local_build_sif_or_sandbox.sh" \
    --release "${RELEASE_NAME}" \
    --current-link "${CURRENT_LINK}" \
    --service-root "${RELAYMD_SERVICE_ROOT}" \
    --mode sif
