#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="relaymd-dashboard"

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

tmux new-session -d -s "${SESSION_NAME}"
tmux send-keys -t "${SESSION_NAME}" "uv run relaymd orchestrator proxy" C-m

echo "started relaymd dashboard proxy in tmux session '${SESSION_NAME}'"
echo "attach: tmux attach -t ${SESSION_NAME}"
echo "stop:   tmux kill-session -t ${SESSION_NAME}"
