#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_sif_or_sandbox.sh [--release <name>] [--mode sif|sandbox] [--current-link <path>] \
    [--worker-profile atom-openmm|gcncmcmd|all] [--atom-openmm-uri <uri>] \
    [--gcncmcmd-uri <uri>] [--orchestrator-uri <uri>] [--service-root <path>]

Build local Apptainer runtime artifacts from OCI/docker URIs.
Default mode is 'sif'.
USAGE
}

RELEASE_NAME="${RELEASE_NAME:-local-dev}"
MODE="${MODE:-sif}"
RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
CURRENT_LINK="${CURRENT_LINK:-}"
ATOM_OPENMM_URI="${ATOM_OPENMM_URI:-docker-daemon://relaymd-worker-atom-openmm:local-dev}"
GCNCMC_URI="${GCNCMC_URI:-docker-daemon://relaymd-worker-gcncmcmd:local-dev}"
WORKER_PROFILE="${WORKER_PROFILE:-all}"
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
        --atom-openmm-uri)
            ATOM_OPENMM_URI="$2"
            shift 2
            ;;
        --gcncmcmd-uri)
            GCNCMC_URI="$2"
            shift 2
            ;;
        --worker-profile)
            WORKER_PROFILE="$2"
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
if [[ "${WORKER_PROFILE}" != "atom-openmm" && "${WORKER_PROFILE}" != "gcncmcmd" && "${WORKER_PROFILE}" != "all" ]]; then
    echo "Invalid --worker-profile '${WORKER_PROFILE}'. Expected atom-openmm|gcncmcmd|all." >&2
    exit 1
fi

if ! command -v apptainer >/dev/null 2>&1; then
    echo "Missing required command 'apptainer'." >&2
    exit 1
fi

RELEASES_DIR="${RELAYMD_SERVICE_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_NAME}"
mkdir -p "${RELEASE_DIR}"

_build_artifact() {
    local label="$1"
    local uri="$2"
    local output="$3"
    local tmp_output="${output}.tmp.$$"

    rm -rf "${tmp_output}"

    if [[ "${MODE}" == "sif" ]]; then
        echo "[${label}] Pulling ${uri} into ${output}"
        apptainer pull "${tmp_output}" "${uri}"
    else
        echo "[${label}] Building sandbox from ${uri} into ${output}"
        apptainer build --sandbox "${tmp_output}" "${uri}"
    fi

    if [[ -e "${output}" ]]; then
        echo "[${label}] Replacing existing local artifact at ${output}"
        rm -rf "${output}"
    fi
    mv "${tmp_output}" "${output}"
}

artifact_extension="sif"
[[ "${MODE}" == "sif" ]] || artifact_extension="sandbox"
orchestrator_output="${RELEASE_DIR}/relaymd-orchestrator.${artifact_extension}"
worker_pids=()
if [[ "${WORKER_PROFILE}" == "atom-openmm" || "${WORKER_PROFILE}" == "all" ]]; then
    _build_artifact "worker-atom-openmm" "${ATOM_OPENMM_URI}" "${RELEASE_DIR}/relaymd-worker-atom-openmm.${artifact_extension}" &
    worker_pids+=("$!")
fi
if [[ "${WORKER_PROFILE}" == "gcncmcmd" || "${WORKER_PROFILE}" == "all" ]]; then
    _build_artifact "worker-gcncmcmd" "${GCNCMC_URI}" "${RELEASE_DIR}/relaymd-worker-gcncmcmd.${artifact_extension}" &
    worker_pids+=("$!")
fi
_build_artifact "orchestrator" "${ORCHESTRATOR_URI}" "${orchestrator_output}" &
ORCH_PID=$!

WORKER_EXIT=0
for worker_pid in "${worker_pids[@]}"; do
    wait "${worker_pid}" || WORKER_EXIT=$?
done
ORCH_EXIT=0; wait "${ORCH_PID}" || ORCH_EXIT=$?
[[ "${WORKER_EXIT}" -eq 0 ]] || echo "[worker] Local artifact build failed (exit ${WORKER_EXIT})." >&2
[[ "${ORCH_EXIT}" -eq 0 ]] || echo "[orchestrator] Local artifact build failed (exit ${ORCH_EXIT})." >&2
[[ "${WORKER_EXIT}" -eq 0 && "${ORCH_EXIT}" -eq 0 ]] || exit 1

if [[ "${MODE}" == "sandbox" ]]; then
    ln -sfn "relaymd-orchestrator.sandbox" "${RELEASE_DIR}/relaymd-orchestrator.sif"
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
