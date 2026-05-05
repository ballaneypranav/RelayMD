#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: local_build_images.sh [--engine auto|docker|podman] [--tag <tag>] [--worker-image <name>] [--orchestrator-image <name>] [--base-image <name>]

Build worker + orchestrator Docker images from the current workspace for local Apptainer conversion.
Defaults:
  tag: local-dev
  worker image: relaymd-worker
  orchestrator image: relaymd-orchestrator
  base image: ghcr.io/your-org/relaymd-base:latest
USAGE
}

ENGINE="${ENGINE:-auto}"
TAG="${TAG:-local-dev}"
WORKER_IMAGE_NAME="${WORKER_IMAGE_NAME:-relaymd-worker}"
ORCHESTRATOR_IMAGE_NAME="${ORCHESTRATOR_IMAGE_NAME:-relaymd-orchestrator}"
BASE_IMAGE="${BASE_IMAGE:-ghcr.io/your-org/relaymd-base:latest}"

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
        --worker-image)
            WORKER_IMAGE_NAME="$2"
            shift 2
            ;;
        --orchestrator-image)
            ORCHESTRATOR_IMAGE_NAME="$2"
            shift 2
            ;;
        --base-image)
            BASE_IMAGE="$2"
            shift 2
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
        echo "  3) Try make local-build-from-def (experimental; requires working apptainer fakeroot)." >&2
        exit 1
    fi
elif ! command -v "${BUILD_ENGINE}" >/dev/null 2>&1; then
    echo "Requested build engine '${BUILD_ENGINE}' is not installed." >&2
    exit 1
fi

WORKER_REF="${WORKER_IMAGE_NAME}:${TAG}"
ORCHESTRATOR_REF="${ORCHESTRATOR_IMAGE_NAME}:${TAG}"

printf 'Using build engine: %s\n' "${BUILD_ENGINE}"
printf 'Building worker image: %s\n' "${WORKER_REF}"
"${BUILD_ENGINE}" build --build-arg BASE_IMAGE="${BASE_IMAGE}" -t "${WORKER_REF}" .

printf 'Building orchestrator image: %s\n' "${ORCHESTRATOR_REF}"
"${BUILD_ENGINE}" build -f Dockerfile.orchestrator -t "${ORCHESTRATOR_REF}" .

cat <<OUT
Built local images:
  worker:       ${WORKER_REF}
  orchestrator: ${ORCHESTRATOR_REF}

Apptainer source URIs:
  worker:       docker-daemon://${WORKER_REF}
  orchestrator: docker-daemon://${ORCHESTRATOR_REF}
OUT
