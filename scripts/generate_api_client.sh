#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_PATH="$ROOT_DIR/packages/relaymd-api-client/openapi.json"
OUTPUT_DIR="$ROOT_DIR/packages/relaymd-api-client/src/relaymd_api_client"

cd "$ROOT_DIR"

: "${UV_CACHE_DIR:=/tmp/uv-cache}"
export UV_CACHE_DIR

# Ensure tool/runtime deps are present without requiring workspace packages.
uv sync --dev --frozen --no-install-workspace

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
VENV_OPENAPI_CLIENT="$ROOT_DIR/.venv/bin/openapi-python-client"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "error: expected virtualenv python at $VENV_PYTHON" >&2
  exit 1
fi
if [[ ! -x "$VENV_OPENAPI_CLIENT" ]]; then
  echo "error: expected openapi-python-client at $VENV_OPENAPI_CLIENT" >&2
  exit 1
fi

export PATH="$ROOT_DIR/.venv/bin:$PATH"

PYTHONPATH="$ROOT_DIR/src:$ROOT_DIR/packages/relaymd-core/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$VENV_PYTHON" -c "import json; from pathlib import Path; from relaymd.orchestrator.main import create_app; Path('$SCHEMA_PATH').write_text(json.dumps(create_app(start_background_tasks=False).openapi(), indent=2), encoding='utf-8')"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

"$VENV_OPENAPI_CLIENT" generate \
  --path "$SCHEMA_PATH" \
  --output-path "$OUTPUT_DIR" \
  --meta none \
  --overwrite
