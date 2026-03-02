ARG BASE_IMAGE=ghcr.io/your-org/relaymd-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app

COPY packages ./packages

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
    ./packages/relaymd-core \
    ./packages/relaymd-api-client \
    ./packages/relaymd-worker

ENTRYPOINT ["python", "-m", "relaymd.worker"]
