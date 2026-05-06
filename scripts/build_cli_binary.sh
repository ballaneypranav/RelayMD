#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

: "${UV_CACHE_DIR:=/tmp/uv-cache}"
export UV_CACHE_DIR
: "${RELAYMD_CLI_BUILD_CLEAN:=0}"

STAGE_ROOT="${ROOT_DIR}/build/relaymd-cli-src"
rm -rf "${STAGE_ROOT}"
mkdir -p "${STAGE_ROOT}/relaymd"

# Stage a single relaymd package tree for PyInstaller.
# This avoids namespace-package resolution gaps between src/ and relaymd-core/.
cp -a "${ROOT_DIR}/packages/relaymd-core/src/relaymd/." "${STAGE_ROOT}/relaymd/"
cp -a "${ROOT_DIR}/src/relaymd/." "${STAGE_ROOT}/relaymd/"

if [[ "${RELAYMD_CLI_BUILD_CLEAN}" == "1" ]]; then
    RELAYMD_CLI_SOURCE_ROOT="${STAGE_ROOT}" \
    RELAYMD_CORE_SOURCE_ROOT="${STAGE_ROOT}" \
    uv run --no-sync pyinstaller --clean relaymd-cli.spec
else
    RELAYMD_CLI_SOURCE_ROOT="${STAGE_ROOT}" \
    RELAYMD_CORE_SOURCE_ROOT="${STAGE_ROOT}" \
    uv run --no-sync pyinstaller relaymd-cli.spec
fi
