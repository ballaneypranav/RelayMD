#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="relaymd"

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    echo "tmux session '${SESSION_NAME}' already running"
    echo "attach: tmux attach -t ${SESSION_NAME}"
    exit 0
fi

tmux new-session -d -s "${SESSION_NAME}"
tmux send-keys -t "${SESSION_NAME}" "uv run relaymd orchestrator up" C-m

echo "started relaymd orchestrator in tmux session '${SESSION_NAME}'"
echo "attach: tmux attach -t ${SESSION_NAME}"
echo "stop:   tmux kill-session -t ${SESSION_NAME}"
