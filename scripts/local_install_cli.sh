#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_install_cli.sh [--target <path>] [--build]

Install locally built RelayMD CLI binary into active service path.
Defaults:
  target: /depot/plow/apps/relaymd/current/relaymd
USAGE
}

TARGET="${TARGET:-/depot/plow/apps/relaymd/current/relaymd}"
BUILD_FIRST=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            if [[ -z "${2-}" || "${2}" == -* ]]; then
                echo "--target requires a non-empty path argument." >&2
                usage >&2
                exit 1
            fi
            TARGET="$2"
            shift 2
            ;;
        --build)
            BUILD_FIRST=1
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

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ "${BUILD_FIRST}" -eq 1 ]]; then
    "${ROOT_DIR}/scripts/build_cli_binary.sh"
fi

SOURCE_BIN="${ROOT_DIR}/dist/relaymd"
if [[ ! -x "${SOURCE_BIN}" ]]; then
    echo "CLI binary not found at ${SOURCE_BIN}. Run scripts/build_cli_binary.sh first or pass --build." >&2
    exit 1
fi

TARGET_DIR="$(dirname "${TARGET}")"
mkdir -p "${TARGET_DIR}"

tmp_target="${TARGET}.tmp.$$"
cp "${SOURCE_BIN}" "${tmp_target}"
chmod 755 "${tmp_target}"
mv "${tmp_target}" "${TARGET}"

"${TARGET}" --version
