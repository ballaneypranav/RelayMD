#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_sif_or_sandbox.sh [--release <name>] [--mode sif|sandbox] [--current-link <path>] \
    [--worker-uri <uri>] [--orchestrator-uri <uri>] [--service-root <path>]

Build local Apptainer runtime artifacts from OCI/docker URIs.
Default mode is 'sif'.
USAGE
}

RELEASE_NAME="${RELEASE_NAME:-local-dev}"
MODE="${MODE:-sif}"
RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
CURRENT_LINK="${CURRENT_LINK:-}"
WORKER_URI="${WORKER_URI:-docker-daemon://relaymd-worker:local-dev}"
ORCHESTRATOR_URI="${ORCHESTRATOR_URI:-docker-daemon://relaymd-orchestrator:local-dev}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)
            RELEASE_NAME="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --current-link)
            CURRENT_LINK="$2"
            shift 2
            ;;
        --worker-uri)
            WORKER_URI="$2"
            shift 2
            ;;
        --orchestrator-uri)
            ORCHESTRATOR_URI="$2"
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

if [[ "${MODE}" != "sif" && "${MODE}" != "sandbox" ]]; then
    echo "Invalid --mode '${MODE}'. Expected 'sif' or 'sandbox'." >&2
    exit 1
fi

if ! command -v apptainer >/dev/null 2>&1; then
    echo "Missing required command 'apptainer'." >&2
    exit 1
fi

RELEASES_DIR="${RELAYMD_SERVICE_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_NAME}"
mkdir -p "${RELEASE_DIR}"

if [[ "${MODE}" == "sif" ]]; then
    apptainer pull "${RELEASE_DIR}/relaymd-worker.sif" "${WORKER_URI}"
    apptainer pull "${RELEASE_DIR}/relaymd-orchestrator.sif" "${ORCHESTRATOR_URI}"
else
    apptainer build --sandbox "${RELEASE_DIR}/relaymd-worker.sandbox" "${WORKER_URI}"
    apptainer build --sandbox "${RELEASE_DIR}/relaymd-orchestrator.sandbox" "${ORCHESTRATOR_URI}"
fi

if [[ -z "${CURRENT_LINK}" ]]; then
    # Recompute default CURRENT_LINK after any --service-root changes
    CURRENT_LINK="${RELAYMD_SERVICE_ROOT}/current"
fi
ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"

cat <<OUT
Local Apptainer artifacts updated.
  release: ${RELEASE_DIR}
  current: ${CURRENT_LINK} -> ${RELEASE_DIR}
  mode:    ${MODE}
OUT
