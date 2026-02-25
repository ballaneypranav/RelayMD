#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_PATH="$ROOT_DIR/packages/relaymd-api-client/openapi.json"
OUTPUT_DIR="$ROOT_DIR/packages/relaymd-api-client"

cd "$ROOT_DIR"

uv run python -c "import json; from relaymd.orchestrator.main import create_app; print(json.dumps(create_app(start_background_tasks=False).openapi(), indent=2))" > "$SCHEMA_PATH"

uv run openapi-python-client generate \
  --path "$SCHEMA_PATH" \
  --output-path "$OUTPUT_DIR" \
  --meta none \
  --overwrite

