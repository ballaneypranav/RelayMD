#!/usr/bin/env bash
set -euo pipefail

echo "relaymd smoke test start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: ${HOSTNAME:-unknown}"
echo "sleeping for 300 seconds to validate heartbeats"
sleep 300
echo "relaymd smoke test end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
