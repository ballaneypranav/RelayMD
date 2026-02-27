#!/usr/bin/env bash
set -euo pipefail

# Run from relaymd/test/
# Required env vars (direct CLI names):
#   RELAYMD_API_TOKEN
#   B2_ENDPOINT_URL
#   B2_BUCKET_NAME
#   B2_ACCESS_KEY_ID
#   B2_SECRET_ACCESS_KEY
# Infisical aliases also supported:
#   B2_ENDPOINT -> B2_ENDPOINT_URL
#   BUCKET_NAME -> B2_BUCKET_NAME
#   B2_APPLICATION_KEY_ID -> B2_ACCESS_KEY_ID
#   B2_APPLICATION_KEY -> B2_SECRET_ACCESS_KEY
# Optional:
#   RELAYMD_CONFIG (defaults to ./relaymd-config.yaml)
#   RELAYMD_ORCHESTRATOR_URL
#   RELAYMD_ORCHESTRATOR_URL_OVERRIDE (applied after Infisical injection)
#   RELAYMD_API_TOKEN_OVERRIDE (applied after Infisical injection)

export B2_ENDPOINT_URL="${B2_ENDPOINT_URL:-${B2_ENDPOINT:-}}"
export B2_BUCKET_NAME="${B2_BUCKET_NAME:-${BUCKET_NAME:-}}"
export B2_ACCESS_KEY_ID="${B2_ACCESS_KEY_ID:-${B2_APPLICATION_KEY_ID:-}}"
export B2_SECRET_ACCESS_KEY="${B2_SECRET_ACCESS_KEY:-${B2_APPLICATION_KEY:-}}"

# boto3 endpoint_url must include a URL scheme.
if [[ -n "${B2_ENDPOINT_URL:-}" && "${B2_ENDPOINT_URL}" != *"://"* ]]; then
  export B2_ENDPOINT_URL="https://${B2_ENDPOINT_URL}"
fi

if [[ -n "${RELAYMD_ORCHESTRATOR_URL_OVERRIDE:-}" ]]; then
  export RELAYMD_ORCHESTRATOR_URL="${RELAYMD_ORCHESTRATOR_URL_OVERRIDE}"
fi

if [[ -n "${RELAYMD_API_TOKEN_OVERRIDE:-}" ]]; then
  export RELAYMD_API_TOKEN="${RELAYMD_API_TOKEN_OVERRIDE}"
fi

REQUIRED_VARS=(
  RELAYMD_API_TOKEN
  B2_ENDPOINT_URL
  B2_BUCKET_NAME
  B2_ACCESS_KEY_ID
  B2_SECRET_ACCESS_KEY
)

for name in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
done

export RELAYMD_CONFIG="${RELAYMD_CONFIG:-./relaymd-config.yaml}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

ORCH_URL_FOR_CHECK=""
if [[ -n "${RELAYMD_ORCHESTRATOR_URL_OVERRIDE:-}" ]]; then
  ORCH_URL_FOR_CHECK="${RELAYMD_ORCHESTRATOR_URL_OVERRIDE}"
elif [[ -f "${RELAYMD_CONFIG}" ]]; then
  CONFIG_ORCH_URL="$(
    awk '
      /^[[:space:]]*orchestrator_url:[[:space:]]*/ {
        sub(/^[[:space:]]*orchestrator_url:[[:space:]]*/, "", $0)
        print
        exit
      }
    ' "${RELAYMD_CONFIG}" \
      | sed 's/[[:space:]]#.*$//;s/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//'
  )"
  ORCH_URL_FOR_CHECK="${CONFIG_ORCH_URL:-${RELAYMD_ORCHESTRATOR_URL:-}}"
else
  ORCH_URL_FOR_CHECK="${RELAYMD_ORCHESTRATOR_URL:-}"
fi

extract_host() {
  local value="$1"
  local no_scheme="${value#*://}"
  local authority="${no_scheme%%/*}"

  # Handle bracketed IPv6 hosts: [addr] or [addr]:port
  if [[ "${authority}" == \[*\]* ]]; then
    local ipv6_host="${authority#\[}"
    echo "${ipv6_host%%\]*}"
    return
  fi

  # Strip optional :port for IPv4/hostname authorities.
  echo "${authority%%:*}"
}

if command -v getent >/dev/null 2>&1; then
  B2_HOST="$(extract_host "${B2_ENDPOINT_URL}")"
  if ! getent hosts "${B2_HOST}" >/dev/null 2>&1; then
    echo "Cannot resolve B2 endpoint host: ${B2_HOST}" >&2
    exit 1
  fi

  if [[ -n "${ORCH_URL_FOR_CHECK:-}" ]]; then
    ORCH_HOST="$(extract_host "${ORCH_URL_FOR_CHECK}")"
    if ! getent hosts "${ORCH_HOST}" >/dev/null 2>&1; then
      echo "Cannot resolve orchestrator host: ${ORCH_HOST}" >&2
      echo "Set RELAYMD_ORCHESTRATOR_URL_OVERRIDE to a reachable URL and retry." >&2
      exit 1
    fi
  fi
fi

uv run relaymd submit sleep-5m --title "sleep-5m-smoke"
