#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_PATH="$ROOT_DIR/packages/relaymd-api-client/openapi.json"
OUTPUT_DIR="$ROOT_DIR/packages/relaymd-api-client/src/relaymd_api_client"

cd "$ROOT_DIR"

: "${UV_CACHE_DIR:=/tmp/uv-cache}"
export UV_CACHE_DIR

uv run python -c "import json; from pathlib import Path; from relaymd.orchestrator.main import create_app; Path('$SCHEMA_PATH').write_text(json.dumps(create_app(start_background_tasks=False).openapi(), indent=2), encoding='utf-8')"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

uv run openapi-python-client generate \
  --path "$SCHEMA_PATH" \
  --output-path "$OUTPUT_DIR" \
  --meta none \
  --overwrite
