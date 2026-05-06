#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_from_def.sh [--release <name>] [--mode sandbox|sif] [--current-link <path>] [--service-root <path>] [--fallback]
                               [--worker-base-sif <path>] [--orchestrator-base-sif <path>]
                               [--rebuild-worker-base] [--rebuild-orchestrator-base] [--rebuild-bases]

Self-contained local-only path:
- Builds worker + orchestrator artifacts from local-source .def files.
- Default mode is sandbox.
- Builds and reuses local base SIFs matching the Docker base layers.
- Optional --fallback uses local_build_sif_or_sandbox.sh if .def build fails.
USAGE
}

RELEASE_NAME="${RELEASE_NAME:-local-def-dev}"
MODE="${MODE:-sandbox}"
FALLBACK=0
RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
CURRENT_LINK="${CURRENT_LINK:-}"
WORKER_BASE_SIF="${WORKER_BASE_SIF:-}"
ORCHESTRATOR_BASE_SIF="${ORCHESTRATOR_BASE_SIF:-}"
REBUILD_WORKER_BASE="${REBUILD_WORKER_BASE:-0}"
REBUILD_ORCHESTRATOR_BASE="${REBUILD_ORCHESTRATOR_BASE:-0}"

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
        --service-root)
            RELAYMD_SERVICE_ROOT="$2"
            shift 2
            ;;
        --fallback)
            FALLBACK=1
            shift
            ;;
        --worker-base-sif)
            WORKER_BASE_SIF="$2"
            shift 2
            ;;
        --orchestrator-base-sif)
            ORCHESTRATOR_BASE_SIF="$2"
            shift 2
            ;;
        --rebuild-worker-base)
            REBUILD_WORKER_BASE=1
            shift
            ;;
        --rebuild-orchestrator-base)
            REBUILD_ORCHESTRATOR_BASE=1
            shift
            ;;
        --rebuild-bases)
            REBUILD_WORKER_BASE=1
            REBUILD_ORCHESTRATOR_BASE=1
            shift
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

if [[ "${MODE}" != "sandbox" && "${MODE}" != "sif" ]]; then
    echo "Invalid --mode '${MODE}'. Expected 'sandbox' or 'sif'." >&2
    exit 1
fi
if [[ -z "${CURRENT_LINK}" ]]; then
    CURRENT_LINK="${RELAYMD_SERVICE_ROOT}/current"
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_BASE_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-worker-base.localdev.def"
ORCHESTRATOR_BASE_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-orchestrator-base.localdev.def"
WORKER_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-worker.localdev.def"
ORCH_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-orchestrator.localdev.def"
RELEASES_DIR="${RELAYMD_SERVICE_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_NAME}"
LOCAL_DEF_STAGE_DIR="${ROOT_DIR}/build/local-def-stage"
if [[ -z "${WORKER_BASE_SIF}" ]]; then
    WORKER_BASE_SIF="${LOCAL_DEF_STAGE_DIR}/relaymd-worker-base.sif"
fi
if [[ -z "${ORCHESTRATOR_BASE_SIF}" ]]; then
    ORCHESTRATOR_BASE_SIF="${LOCAL_DEF_STAGE_DIR}/relaymd-orchestrator-base.sif"
fi

if ! command -v apptainer >/dev/null 2>&1; then
    echo "Missing required command 'apptainer'." >&2
    exit 1
fi

mkdir -p "${RELEASE_DIR}"
cd "${ROOT_DIR}"

stage_dir="${LOCAL_DEF_STAGE_DIR}"
stage_frontend_dir="${stage_dir}/frontend-min"
mkdir -p "${stage_dir}"
rm -rf "${stage_frontend_dir}"
mkdir -p "${stage_frontend_dir}"

copy_if_exists() {
    local src="$1"
    local dst="$2"
    if [[ -e "${src}" ]]; then
        cp -a "${src}" "${dst}"
    fi
}

# Stage only frontend build inputs to avoid copying node_modules/.npm/dist/coverage.
cp -a "${ROOT_DIR}/frontend/package.json" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/package-lock.json" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/index.html" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/tsconfig.json" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/tsconfig.app.json" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/tsconfig.node.json" "${stage_frontend_dir}/"
copy_if_exists "${ROOT_DIR}/frontend/vite.config.ts" "${stage_frontend_dir}/"
cp -a "${ROOT_DIR}/frontend/src" "${stage_frontend_dir}/src"
if [[ -d "${ROOT_DIR}/frontend/public" ]]; then
    cp -a "${ROOT_DIR}/frontend/public" "${stage_frontend_dir}/public"
fi
if [[ -d "${ROOT_DIR}/frontend/scripts" ]]; then
    cp -a "${ROOT_DIR}/frontend/scripts" "${stage_frontend_dir}/scripts"
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/relaymd-local-def.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
orch_def_staged="${tmp_dir}/relaymd-orchestrator.localdev.staged.def"
worker_def_staged="${tmp_dir}/relaymd-worker.localdev.staged.def"

# Point orchestrator %files frontend source at staged minimal tree.
sed "s#^    frontend /opt/relaymd/frontend#    build/local-def-stage/frontend-min /opt/relaymd/frontend#" \
    "${ORCH_DEF}" > "${orch_def_staged}"
# Point orchestrator bootstrap source at caller-provided local base SIF.
sed -i "s#^From: .*#From: ${ORCHESTRATOR_BASE_SIF}#" "${orch_def_staged}"
# Point worker bootstrap source at caller-provided local base SIF.
sed "s#^From: .*#From: ${WORKER_BASE_SIF}#" "${WORKER_DEF}" > "${worker_def_staged}"

if [[ "${MODE}" == "sandbox" ]]; then
    worker_output="${RELEASE_DIR}/relaymd-worker.sandbox"
    orch_output="${RELEASE_DIR}/relaymd-orchestrator.sandbox"
    rm -rf "${worker_output}" "${orch_output}"
else
    worker_output="${RELEASE_DIR}/relaymd-worker.sif"
    orch_output="${RELEASE_DIR}/relaymd-orchestrator.sif"
fi

set +e
if [[ "${REBUILD_WORKER_BASE}" == "1" || ! -f "${WORKER_BASE_SIF}" ]]; then
    mkdir -p "$(dirname "${WORKER_BASE_SIF}")"
    worker_base_tmp="${WORKER_BASE_SIF}.tmp.$$"
    rm -f "${worker_base_tmp}"
    apptainer build --fakeroot "${worker_base_tmp}" "${WORKER_BASE_DEF}"
    worker_base_rc=$?
    if [[ "${worker_base_rc}" -eq 0 ]]; then
        mv "${worker_base_tmp}" "${WORKER_BASE_SIF}"
    else
        rm -f "${worker_base_tmp}"
    fi
else
    worker_base_rc=0
fi
if [[ "${REBUILD_ORCHESTRATOR_BASE}" == "1" || ! -f "${ORCHESTRATOR_BASE_SIF}" ]]; then
    mkdir -p "$(dirname "${ORCHESTRATOR_BASE_SIF}")"
    orch_base_tmp="${ORCHESTRATOR_BASE_SIF}.tmp.$$"
    rm -f "${orch_base_tmp}"
    apptainer build --fakeroot "${orch_base_tmp}" "${ORCHESTRATOR_BASE_DEF}"
    orch_base_rc=$?
    if [[ "${orch_base_rc}" -eq 0 ]]; then
        mv "${orch_base_tmp}" "${ORCHESTRATOR_BASE_SIF}"
    else
        rm -f "${orch_base_tmp}"
    fi
else
    orch_base_rc=0
fi
if [[ "${MODE}" == "sandbox" ]]; then
    apptainer build --fakeroot --sandbox "${worker_output}" "${worker_def_staged}"
else
    apptainer build --fakeroot "${worker_output}" "${worker_def_staged}"
fi
worker_rc=$?
if [[ "${MODE}" == "sandbox" ]]; then
    apptainer build --fakeroot --sandbox "${orch_output}" "${orch_def_staged}"
else
    apptainer build --fakeroot "${orch_output}" "${orch_def_staged}"
fi
orch_rc=$?
set -e

if [[ "${worker_base_rc}" -eq 0 && "${orch_base_rc}" -eq 0 && "${worker_rc}" -eq 0 && "${orch_rc}" -eq 0 ]]; then
    if [[ "${MODE}" == "sandbox" ]]; then
        ln -sfn "relaymd-worker.sandbox" "${RELEASE_DIR}/relaymd-worker.sif"
        ln -sfn "relaymd-orchestrator.sandbox" "${RELEASE_DIR}/relaymd-orchestrator.sif"
    fi
    ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"
    cat <<OUT
Self-contained .def build succeeded.
  release: ${RELEASE_DIR}
  current: ${CURRENT_LINK} -> ${RELEASE_DIR}
  mode:    ${MODE}
  worker base: ${WORKER_BASE_SIF}
  orchestrator base: ${ORCHESTRATOR_BASE_SIF}
OUT
    exit 0
fi

if [[ "${FALLBACK}" -eq 1 ]]; then
    echo "Self-contained .def build failed; using fallback local OCI->Apptainer flow." >&2
    "${ROOT_DIR}/scripts/local_build_sif_or_sandbox.sh" \
        --release "${RELEASE_NAME}" \
        --current-link "${CURRENT_LINK}" \
        --service-root "${RELAYMD_SERVICE_ROOT}" \
        --mode "${MODE}"
    exit 0
fi

echo "Self-contained .def build failed." >&2
echo "No fallback executed. Re-run with --fallback to try local OCI->Apptainer flow." >&2
exit 1
