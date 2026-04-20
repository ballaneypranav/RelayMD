#!/usr/bin/env bash
set -euo pipefail

RELAYMD_SERVICE_ROOT="${RELAYMD_SERVICE_ROOT:-/depot/plow/apps/relaymd}"
RELAYMD_DATA_ROOT="${RELAYMD_DATA_ROOT:-/depot/plow/data/pballane/relaymd-service}"
MODULEFILES_ROOT="${MODULEFILES_ROOT:-/depot/plow/apps/modulefiles}"
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

echo "Installed wrappers to: ${BIN_DIR}"
echo "Installed CLI wrapper: ${BIN_DIR}/relaymd"
echo "Modulefile: ${MODULEFILE_PATH}"
echo "Config file: ${CONFIG_DIR}/relaymd-config.yaml"
echo "Env file: ${CONFIG_DIR}/relaymd-service.env"
echo "Status file: ${STATE_DIR}/relaymd-service.status"
