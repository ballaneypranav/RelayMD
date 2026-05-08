#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="relaymd-dashboard"

if [[ -z "${INFISICAL_TOKEN:-}" ]]; then
    echo "INFISICAL_TOKEN is required"
    exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    echo "tmux session '${SESSION_NAME}' already running"
    echo "attach: tmux attach -t ${SESSION_NAME}"
    exit 0
fi

printf -v INFISICAL_TOKEN_Q "%q" "${INFISICAL_TOKEN}"

tmux new-session -d -s "${SESSION_NAME}" \
    "env INFISICAL_TOKEN=${INFISICAL_TOKEN_Q} uv run relaymd-dashboard-proxy"

echo "started relaymd dashboard proxy in tmux session '${SESSION_NAME}'"
echo "attach: tmux attach -t ${SESSION_NAME}"
echo "stop:   tmux kill-session -t ${SESSION_NAME}"
