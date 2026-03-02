ARG BASE_IMAGE=ghcr.io/ballaneypranav/relaymd-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages ./packages

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
    ./packages/relaymd-core \
    ./packages/relaymd-api-client \
    ./packages/relaymd-worker

ENTRYPOINT ["python", "-m", "relaymd.worker"]
