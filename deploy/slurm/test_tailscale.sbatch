#!/bin/bash
#SBATCH --job-name=relaymd-tailscale-test
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G

set -euo pipefail

if [[ -z "${TAILSCALE_AUTH_KEY:-}" ]]; then
  echo "TAILSCALE_AUTH_KEY must be set"
  exit 2
fi

if [[ -z "${ORCHESTRATOR_HOSTNAME:-}" ]]; then
  echo "ORCHESTRATOR_HOSTNAME must be set (MagicDNS host, no scheme/port)"
  exit 2
fi

if [[ -z "${RELAYMD_SIF_PATH:-}" ]]; then
  echo "RELAYMD_SIF_PATH must point to relaymd.sif"
  exit 2
fi

APPTAINER_FLAGS=${APPTAINER_FLAGS:-"--cleanenv --writable-tmpfs --bind /tmp:/tmp"}
RUN_ID="${SLURM_JOB_ID:-manual}-$(hostname)"
CONTAINER_HOSTNAME="relaymd-test-${RUN_ID}"
LOG_FILE="tailscale-healthz-${RUN_ID}.log"

echo "Using image: ${RELAYMD_SIF_PATH}"
echo "Apptainer flags: ${APPTAINER_FLAGS}"
echo "Container hostname: ${CONTAINER_HOSTNAME}"

# shellcheck disable=SC2086
apptainer exec ${APPTAINER_FLAGS} "${RELAYMD_SIF_PATH}" /bin/bash -lc '
  set -euo pipefail
  cleanup() {
    if [[ -n "${TS_PID:-}" ]]; then
      kill "${TS_PID}" >/dev/null 2>&1 || true
      wait "${TS_PID}" >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT

  tailscaled \
    --tun=userspace-networking \
    --statedir=/tmp/tailscale-state \
    --socket=/tmp/tailscaled.sock \
    >/tmp/tailscaled.log 2>&1 &
  TS_PID=$!

  tailscaled_ready=0
  for _ in $(seq 1 30); do
    if tailscale --socket=/tmp/tailscaled.sock status >/dev/null 2>&1; then
      tailscaled_ready=1
      break
    fi
    sleep 1
  done
  if [[ "${tailscaled_ready}" -ne 1 ]]; then
    echo "tailscaled did not become ready within 30 seconds" >&2
    echo "tailscaled log follows:" >&2
    cat /tmp/tailscaled.log >&2 || true
    exit 1
  fi

  tailscale \
    --socket=/tmp/tailscaled.sock \
    up \
    --authkey='"${TAILSCALE_AUTH_KEY}"' \
    --hostname='"${CONTAINER_HOSTNAME}"'

  curl --fail --silent --show-error \
    "http://'"${ORCHESTRATOR_HOSTNAME}"':8000/healthz" \
    | tee "'"${LOG_FILE}"'"
'

grep -q '"status":"ok"' "${LOG_FILE}"
echo "Tailscale userspace + orchestrator healthz test passed"
