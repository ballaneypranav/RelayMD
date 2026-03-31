#!/usr/bin/env bash
set -euo pipefail

checkpoint_file="checkpoint.chk"
downloaded_checkpoint="../latest"
iterations="${CHECKPOINT_TEST_ITERATIONS:-8}"
sleep_seconds="${CHECKPOINT_TEST_SLEEP_SECONDS:-60}"
start_iteration=0

echo "relaymd checkpoint handoff test start: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hostname: ${HOSTNAME:-unknown}"
echo "writing ${checkpoint_file} up to iteration ${iterations} every ${sleep_seconds}s"

read_iteration() {
  local source_file="$1"
  local saved_iteration
  saved_iteration="$(awk -F= '$1 == "iteration" { print $2 }' "${source_file}" | tail -n 1)"
  if [[ -z "${saved_iteration}" ]]; then
    echo "0"
    return
  fi
  echo "${saved_iteration}"
}

if [[ -f "${downloaded_checkpoint}" ]]; then
  resume_iteration="$(read_iteration "${downloaded_checkpoint}")"
  if [[ "${resume_iteration}" =~ ^[0-9]+$ ]] && [[ "${resume_iteration}" -gt 0 ]]; then
    start_iteration="${resume_iteration}"
    echo "resuming from checkpoint iteration ${resume_iteration} via ${downloaded_checkpoint}"
  else
    echo "downloaded checkpoint found at ${downloaded_checkpoint} but iteration was invalid; starting from 0"
  fi
else
  echo "no downloaded checkpoint found; starting from iteration 0"
fi

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

for iteration in $(seq $((start_iteration + 1)) "${iterations}"); do
  write_checkpoint "${iteration}"
  if [[ "${iteration}" -lt "${iterations}" ]]; then
    sleep "${sleep_seconds}"
  fi
done

echo "relaymd checkpoint handoff test end: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
