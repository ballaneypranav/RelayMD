#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_smoke.sh [relaymd-binary]

Fast local smoke checks:
- relaymd --version
- relaymd status --json
- uv run pytest tests/cli/test_build_cli_binary_script.py
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

RELAYMD_BIN="${1:-relaymd}"

"${RELAYMD_BIN}" --version
"${RELAYMD_BIN}" status --json
uv run pytest tests/cli/test_build_cli_binary_script.py
