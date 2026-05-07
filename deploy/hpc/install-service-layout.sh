#!/usr/bin/env bash
set -euo pipefail

DEFAULT_DEPOT_SERVICE_ROOT="/depot/plow/apps/relaymd"
DEFAULT_DEPOT_DATA_ROOT="/depot/plow/data/pballane/relaymd-service"
DEFAULT_DEPOT_MODULEFILES_ROOT="/depot/plow/apps/modulefiles"
DEFAULT_SCRATCH_APPS_ROOT="/scratch/gilbreth/pballane/apps"
DEFAULT_SCRATCH_SERVICE_ROOT="${DEFAULT_SCRATCH_APPS_ROOT}/relaymd"
DEFAULT_SCRATCH_DATA_ROOT="${DEFAULT_SCRATCH_APPS_ROOT}/relaymd-service"
DEFAULT_SCRATCH_MODULEFILES_ROOT="${DEFAULT_SCRATCH_APPS_ROOT}/modulefiles"

usage() {
    cat <<'EOF'
Usage: install-service-layout.sh [--scratch]

Options:
  --scratch  Install RelayMD under /scratch/gilbreth/pballane/apps instead of /depot.
  -h, --help Show this help text.

Environment overrides still take precedence:
  RELAYMD_SERVICE_ROOT
  RELAYMD_DATA_ROOT
  MODULEFILES_ROOT
EOF
}

use_scratch=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scratch)
            use_scratch=1
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

if [[ ${use_scratch} -eq 1 ]]; then
    default_service_root="${DEFAULT_SCRATCH_SERVICE_ROOT}"
    default_data_root="${DEFAULT_SCRATCH_DATA_ROOT}"
    default_modulefiles_root="${DEFAULT_SCRATCH_MODULEFILES_ROOT}"
else
    default_service_root="${DEFAULT_DEPOT_SERVICE_ROOT}"
    default_data_root="${DEFAULT_DEPOT_DATA_ROOT}"
    default_modulefiles_root="${DEFAULT_DEPOT_MODULEFILES_ROOT}"
fi

RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-${default_service_root}}"
RELAYMD_DATA_ROOT="${RELAYMD_DATA_ROOT:-${default_data_root}}"
MODULEFILES_ROOT="${MODULEFILES_ROOT:-${default_modulefiles_root}}"
MODULE_NAME="${MODULE_NAME:-relaymd}"
MODULE_VERSION="${MODULE_VERSION:-current}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CURRENT_DIR="${RELAYMD_SERVICE_ROOT}/current"
BIN_DIR="${RELAYMD_SERVICE_ROOT}/bin"
CONFIG_DIR="${RELAYMD_DATA_ROOT}/config"
STATE_DIR="${RELAYMD_DATA_ROOT}/state"
MODULEFILE_DIR="${MODULEFILES_ROOT}/${MODULE_NAME}"
MODULEFILE_PATH="${MODULEFILE_DIR}/${MODULE_VERSION}.lua"

mkdir -p "${BIN_DIR}" "${CONFIG_DIR}" "${STATE_DIR}" "${MODULEFILE_DIR}"

if [[ -d "${CURRENT_DIR}" && ! -L "${CURRENT_DIR}" ]]; then
    echo "WARNING: ${CURRENT_DIR} is a directory." >&2
    echo "relaymd-service-pull expects ${CURRENT_DIR} to be a symlink to a release dir." >&2
    echo "Wrappers are now installed to ${BIN_DIR} so current can be repointed as a symlink." >&2
fi

install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd-service-pull" "${BIN_DIR}/relaymd-service-pull"
install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd-service-up" "${BIN_DIR}/relaymd-service-up"
install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd-service-proxy" "${BIN_DIR}/relaymd-service-proxy"
install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd-service-status" "${BIN_DIR}/relaymd-service-status"
install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd-service-supervise" "${BIN_DIR}/relaymd-service-supervise"
install -m 0755 "${REPO_ROOT}/deploy/hpc/relaymd" "${BIN_DIR}/relaymd"
install -m 0644 "${REPO_ROOT}/deploy/hpc/relaymd-service-lib.sh" "${BIN_DIR}/relaymd-service-lib.sh"

if [[ ! -f "${CONFIG_DIR}/relaymd-config.yaml" ]]; then
    install -m 0644 "${REPO_ROOT}/deploy/config.example.yaml" "${CONFIG_DIR}/relaymd-config.yaml"
fi

if [[ ! -f "${CONFIG_DIR}/relaymd-service.env" ]]; then
    install -m 0600 "${REPO_ROOT}/deploy/hpc/relaymd-service.env.example" "${CONFIG_DIR}/relaymd-service.env"
fi

sed \
    -e "s|/depot/plow/apps/relaymd|${RELAYMD_SERVICE_ROOT}|g" \
    -e "s|/depot/plow/data/pballane/relaymd-service|${RELAYMD_DATA_ROOT}|g" \
    "${REPO_ROOT}/deploy/hpc/modulefiles/relaymd.lua" > "${MODULEFILE_PATH}"
chmod 0644 "${MODULEFILE_PATH}"

if [[ ${use_scratch} -eq 1 ]]; then
    echo "Install mode: scratch"
fi
echo "Installed wrappers to: ${BIN_DIR}"
echo "Installed CLI wrapper: ${BIN_DIR}/relaymd"
echo "Modulefile: ${MODULEFILE_PATH}"
echo "Config file: ${CONFIG_DIR}/relaymd-config.yaml"
echo "Env file: ${CONFIG_DIR}/relaymd-service.env"
echo "Status file: ${STATE_DIR}/relaymd-service.status"
