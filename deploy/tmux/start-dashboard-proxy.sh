#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="relaymd-dashboard"

if [[ -z "${RELAYMD_API_TOKEN:-}" ]]; then
    echo "RELAYMD_API_TOKEN is required"
    exit 1
fi

if [[ -z "${RELAYMD_DASHBOARD_USERNAME:-}" ]]; then
    echo "RELAYMD_DASHBOARD_USERNAME is required"
    exit 1
fi

if [[ -z "${RELAYMD_DASHBOARD_PASSWORD:-}" ]]; then
    echo "RELAYMD_DASHBOARD_PASSWORD is required"
    exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    echo "tmux session '${SESSION_NAME}' already running"
    echo "attach: tmux attach -t ${SESSION_NAME}"
    exit 0
fi

printf -v RELAYMD_API_TOKEN_Q "%q" "${RELAYMD_API_TOKEN}"
printf -v RELAYMD_DASHBOARD_USERNAME_Q "%q" "${RELAYMD_DASHBOARD_USERNAME}"
printf -v RELAYMD_DASHBOARD_PASSWORD_Q "%q" "${RELAYMD_DASHBOARD_PASSWORD}"

tmux new-session -d -s "${SESSION_NAME}" \
    "env RELAYMD_API_TOKEN=${RELAYMD_API_TOKEN_Q} RELAYMD_DASHBOARD_USERNAME=${RELAYMD_DASHBOARD_USERNAME_Q} RELAYMD_DASHBOARD_PASSWORD=${RELAYMD_DASHBOARD_PASSWORD_Q} uv run relaymd orchestrator proxy"

echo "started relaymd dashboard proxy in tmux session '${SESSION_NAME}'"
echo "attach: tmux attach -t ${SESSION_NAME}"
echo "stop:   tmux kill-session -t ${SESSION_NAME}"
