#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_images.sh [--engine auto|docker|podman] [--tag <tag>] [--worker-profile atom-openmm|gcncmcmd|all] [--orchestrator-image <name>]

Build worker + orchestrator Docker images from the current workspace for local Apptainer conversion.
Defaults:
  tag: local-dev
  worker images: relaymd-worker-atom-openmm and relaymd-worker-gcncmcmd
  orchestrator image: relaymd-orchestrator
USAGE
}

ENGINE="${ENGINE:-auto}"
TAG="${TAG:-local-dev}"
ORCHESTRATOR_IMAGE_NAME="${ORCHESTRATOR_IMAGE_NAME:-relaymd-orchestrator}"
WORKER_PROFILE="${WORKER_PROFILE:-all}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine)
            ENGINE="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --worker-profile)
            WORKER_PROFILE="$2"
            shift 2
            ;;
        --orchestrator-image)
            ORCHESTRATOR_IMAGE_NAME="$2"
            shift 2
            ;;
        --base-image)
            echo "--base-image is no longer supported: worker profiles build their own base images." >&2
            exit 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac

done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ "${ENGINE}" != "auto" && "${ENGINE}" != "docker" && "${ENGINE}" != "podman" ]]; then
    echo "Invalid --engine '${ENGINE}'. Expected auto|docker|podman." >&2
    exit 1
fi

BUILD_ENGINE="${ENGINE}"
if [[ "${BUILD_ENGINE}" == "auto" ]]; then
    if command -v docker >/dev/null 2>&1; then
        BUILD_ENGINE="docker"
    elif command -v podman >/dev/null 2>&1; then
        BUILD_ENGINE="podman"
    else
        echo "Missing local container build engine: neither 'docker' nor 'podman' is available." >&2
        echo "Remediation options:" >&2
        echo "  1) Install Docker or Podman, then rerun make local-build-images." >&2
        echo "  2) Use prebuilt GHCR images via relaymd upgrade <sha|latest> (no local image build)." >&2
        echo "  3) Build on a host with Docker or Podman, then convert the named images with make local-build-sif-or-sandbox." >&2
        exit 1
    fi
elif ! command -v "${BUILD_ENGINE}" >/dev/null 2>&1; then
    echo "Requested build engine '${BUILD_ENGINE}' is not installed." >&2
    exit 1
fi

ORCHESTRATOR_REF="${ORCHESTRATOR_IMAGE_NAME}:${TAG}"
WORKER_REFS=()

printf 'Using build engine: %s\n' "${BUILD_ENGINE}"
if [[ "${WORKER_PROFILE}" != "atom-openmm" && "${WORKER_PROFILE}" != "gcncmcmd" && "${WORKER_PROFILE}" != "all" ]]; then
    echo "Invalid --worker-profile '${WORKER_PROFILE}'. Expected atom-openmm|gcncmcmd|all." >&2
    exit 1
fi
for profile in atom-openmm gcncmcmd; do
    [[ "${WORKER_PROFILE}" == "all" || "${WORKER_PROFILE}" == "${profile}" ]] || continue
    base_ref="relaymd-worker-${profile}-base:${TAG}"
    worker_ref="relaymd-worker-${profile}:${TAG}"
    printf 'Building %s worker base: %s\n' "${profile}" "${base_ref}"
    "${BUILD_ENGINE}" build -f "Dockerfile.worker-${profile}-base" -t "${base_ref}" .
    printf 'Building %s worker image: %s\n' "${profile}" "${worker_ref}"
    "${BUILD_ENGINE}" build -f Dockerfile.worker --build-arg BASE_IMAGE="${base_ref}" -t "${worker_ref}" .
    WORKER_REFS+=("${worker_ref}")
done

printf 'Building orchestrator image: %s\n' "${ORCHESTRATOR_REF}"
"${BUILD_ENGINE}" build -f Dockerfile.orchestrator -t "${ORCHESTRATOR_REF}" .

cat <<OUT
Built local images:
$(for worker_ref in "${WORKER_REFS[@]}"; do printf '  worker:       %s\n' "${worker_ref}"; done)
  orchestrator: ${ORCHESTRATOR_REF}

Apptainer source URIs:
$(for worker_ref in "${WORKER_REFS[@]}"; do printf '  worker:       docker-daemon://%s\n' "${worker_ref}"; done)
  orchestrator: docker-daemon://${ORCHESTRATOR_REF}
OUT
