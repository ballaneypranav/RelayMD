#!/usr/bin/env bash
set -euo pipefail

checkpoint_file="checkpoint.chk"
iterations="${CHECKPOINT_TEST_ITERATIONS:-5}"
sleep_seconds="${CHECKPOINT_TEST_SLEEP_SECONDS:-60}"

echo "relaymd checkpoint test start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: ${HOSTNAME:-unknown}"
echo "writing ${checkpoint_file} ${iterations} times every ${sleep_seconds}s"

write_checkpoint() {
  local iteration="$1"
  local timestamp
  local checkpoint_tmp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  checkpoint_tmp="${checkpoint_file}.tmp"
  cat > "${checkpoint_tmp}" <<EOF
iteration=${iteration}
timestamp=${timestamp}
hostname=${HOSTNAME:-unknown}
EOF
  mv "${checkpoint_tmp}" "${checkpoint_file}"
  echo "checkpoint write ${iteration}/${iterations}: ${timestamp}"
}

for iteration in $(seq 1 "${iterations}"); do
  write_checkpoint "${iteration}"
  if [[ "${iteration}" -lt "${iterations}" ]]; then
    sleep "${sleep_seconds}"
  fi
done

echo "relaymd checkpoint test end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
