#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

: "${UV_CACHE_DIR:=/tmp/uv-cache}"
export UV_CACHE_DIR

"$ROOT_DIR/scripts/generate_api_client.sh"

# Install full workspace now that the generated client package exists.
uv sync --dev --frozen
