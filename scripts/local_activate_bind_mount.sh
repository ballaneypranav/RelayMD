#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_activate_bind_mount.sh [--release <name>] [--current-link <path>] [--service-root <path>]
                                    [--worker-base-sif <path>] [--orchestrator-base-sif <path>]
                                    [--rebuild-worker-base] [--rebuild-orchestrator-base] [--rebuild-bases]
                                    [--env-file <path>] [--base-env-file <path>]

Activate local development runtime artifacts that bind-mount this checkout into
the reusable worker and orchestrator base SIFs. No app-layer .def build is run.

The generated env file sources the normal service env file first, then overrides
only local bind-mount development settings.
USAGE
}

RELEASE_NAME="${RELEASE_NAME:-local-bind-dev}"
RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
CURRENT_LINK="${CURRENT_LINK:-${RELAYMD_SERVICE_ROOT}/current}"
RELAYMD_DATA_ROOT="${RELAYMD_DATA_ROOT:-/depot/plow/data/pballane/relaymd-service}"
BASE_ENV_FILE="${BASE_ENV_FILE:-${RELAYMD_DATA_ROOT}/config/relaymd-service.env}"
OUTPUT_ENV_FILE="${OUTPUT_ENV_FILE:-${RELAYMD_DATA_ROOT}/config/relaymd-local-bind.env}"
BIN_DIR="${RELAYMD_SERVICE_ROOT}/bin"
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
        --current-link)
            CURRENT_LINK="$2"
            shift 2
            ;;
        --service-root)
            RELAYMD_SERVICE_ROOT="$2"
            shift 2
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
        --env-file)
            OUTPUT_ENV_FILE="$2"
            shift 2
            ;;
        --base-env-file)
            BASE_ENV_FILE="$2"
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
LOCAL_DEF_STAGE_DIR="${ROOT_DIR}/build/local-def-stage"
WORKER_BASE_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-worker-base.localdev.def"
ORCHESTRATOR_BASE_DEF="${ROOT_DIR}/deploy/hpc/apptainer/relaymd-orchestrator-base.localdev.def"
RELEASES_DIR="${RELAYMD_SERVICE_ROOT}/releases"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_NAME}"
MOUNT_ROOT="/opt/relaymd-src"
PYTHONPATH_VALUE="${MOUNT_ROOT}/src:${MOUNT_ROOT}/packages/relaymd-core/src:${MOUNT_ROOT}/packages/relaymd-api-client/src:${MOUNT_ROOT}/packages/relaymd-worker/src"
SOURCE_BIND="${ROOT_DIR}:${MOUNT_ROOT}"
DATA_BIND="${RELAYMD_DATA_ROOT}:${RELAYMD_DATA_ROOT}"

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

mkdir -p "${LOCAL_DEF_STAGE_DIR}" "${RELEASE_DIR}" "$(dirname "${OUTPUT_ENV_FILE}")" "${BIN_DIR}"

if [[ "${REBUILD_WORKER_BASE}" != "1" && -f "${WORKER_BASE_SIF}" ]]; then
    if ! apptainer exec "${WORKER_BASE_SIF}" python - <<'PY' >/dev/null 2>&1
import httpx
import infisical_client
import orjson
import pydantic_settings
import structlog
PY
    then
        echo "Existing worker base is missing bind-dev dependencies; rebuilding." >&2
        REBUILD_WORKER_BASE=1
    fi
fi

if [[ "${REBUILD_ORCHESTRATOR_BASE}" != "1" && -f "${ORCHESTRATOR_BASE_SIF}" ]]; then
    if ! apptainer exec "${ORCHESTRATOR_BASE_SIF}" python - <<'PY' >/dev/null 2>&1
import fastapi
import infisical_client
import pydantic_settings
import sqlmodel
import uvicorn
PY
    then
        echo "Existing orchestrator base is missing bind-dev dependencies; rebuilding." >&2
        REBUILD_ORCHESTRATOR_BASE=1
    fi
fi

if [[ "${REBUILD_WORKER_BASE}" == "1" || ! -f "${WORKER_BASE_SIF}" ]]; then
    echo "Building worker base SIF: ${WORKER_BASE_SIF}"
    worker_base_tmp="${WORKER_BASE_SIF}.tmp.$$"
    rm -f "${worker_base_tmp}"
    apptainer build --fakeroot "${worker_base_tmp}" "${WORKER_BASE_DEF}"
    mv "${worker_base_tmp}" "${WORKER_BASE_SIF}"
fi

if [[ "${REBUILD_ORCHESTRATOR_BASE}" == "1" || ! -f "${ORCHESTRATOR_BASE_SIF}" ]]; then
    echo "Building orchestrator base SIF: ${ORCHESTRATOR_BASE_SIF}"
    orchestrator_base_tmp="${ORCHESTRATOR_BASE_SIF}.tmp.$$"
    rm -f "${orchestrator_base_tmp}"
    apptainer build --fakeroot "${orchestrator_base_tmp}" "${ORCHESTRATOR_BASE_DEF}"
    mv "${orchestrator_base_tmp}" "${ORCHESTRATOR_BASE_SIF}"
fi

ln -sfn "${WORKER_BASE_SIF}" "${RELEASE_DIR}/relaymd-worker.sif"
ln -sfn "${ORCHESTRATOR_BASE_SIF}" "${RELEASE_DIR}/relaymd-orchestrator.sif"
cat > "${RELEASE_DIR}/relaymd" <<CLI
#!/usr/bin/env bash
set -euo pipefail
cd "${ROOT_DIR}"
exec uv run --project "${ROOT_DIR}" relaymd "\$@"
CLI
chmod 755 "${RELEASE_DIR}/relaymd"

install -m 0755 "${ROOT_DIR}/deploy/hpc/relaymd-service-up" "${BIN_DIR}/relaymd-service-up"
install -m 0755 "${ROOT_DIR}/deploy/hpc/relaymd-service-proxy" "${BIN_DIR}/relaymd-service-proxy"
install -m 0755 "${ROOT_DIR}/deploy/hpc/relaymd-service-status" "${BIN_DIR}/relaymd-service-status"
install -m 0755 "${ROOT_DIR}/deploy/hpc/relaymd-service-supervise" "${BIN_DIR}/relaymd-service-supervise"
install -m 0755 "${ROOT_DIR}/deploy/hpc/relaymd" "${BIN_DIR}/relaymd"
install -m 0644 "${ROOT_DIR}/deploy/hpc/relaymd-service-lib.sh" "${BIN_DIR}/relaymd-service-lib.sh"
ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"

if [[ ! -f "${ROOT_DIR}/frontend/dist/index.html" ]]; then
    echo "WARNING: frontend/dist/index.html is missing; run 'make frontend-build' before starting the bind-mounted orchestrator." >&2
fi

cat > "${OUTPUT_ENV_FILE}" <<ENV
# Generated by scripts/local_activate_bind_mount.sh.
# Sources the normal service env first, then overrides only local bind settings.
if [ -f "${BASE_ENV_FILE}" ]; then
    . "${BASE_ENV_FILE}"
fi

export RELAYMD_ORCHESTRATOR_SIF="${RELEASE_DIR}/relaymd-orchestrator.sif"
export RELAYMD_BIND_PATHS="${DATA_BIND},${SOURCE_BIND}"
export RELAYMD_ORCHESTRATOR_COMMAND='PYTHONPATH="${PYTHONPATH_VALUE}" RELAYMD_FRONTEND_DIST_DIR="${MOUNT_ROOT}/frontend/dist" python -c "from relaymd.orchestrator.main import start; start()"'
export RELAYMD_PROXY_COMMAND='PYTHONPATH="${PYTHONPATH_VALUE}" python -c "from relaymd.dashboard_proxy_main import start; start()"'
export RELAYMD_WORKER_BIND_PATHS="${SOURCE_BIND}"
export RELAYMD_WORKER_PYTHONPATH="${PYTHONPATH_VALUE}"
export RELAYMD_WORKER_COMMAND="python -m relaymd.worker"
ENV

cat <<OUT
Bind-mounted local runtime activated.
  release:        ${RELEASE_DIR}
  current:        ${CURRENT_LINK} -> ${RELEASE_DIR}
  cli:            ${RELEASE_DIR}/relaymd
  wrappers:       ${BIN_DIR}
  worker base:    ${WORKER_BASE_SIF}
  orchestrator:   ${ORCHESTRATOR_BASE_SIF}
  mounted source: ${ROOT_DIR} -> ${MOUNT_ROOT}
  env overlay:    ${OUTPUT_ENV_FILE}

Start/restart with:
  RELAYMD_ENV_FILE="${OUTPUT_ENV_FILE}" relaymd restart
OUT
