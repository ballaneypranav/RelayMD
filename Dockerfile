FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common ca-certificates gnupg \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && mkdir -p --mode=0755 /usr/share/keyrings \
    && curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg \
    && curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-distutils \
        python3.11-venv \
        git \
        wget \
        curl \
        tailscale \
    && ln -sf /usr/bin/python3.11 /usr/local/bin/python \
    && python3.11 -m ensurepip --upgrade \
    && python -m pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# AToM-OpenMM requires OpenMM plus configobj and numpy.
RUN python -m pip install --no-cache-dir \
    "openmm>=8.4" \
    configobj \
    numpy \
    setproctitle \
    atom-openmm

COPY packages ./packages

RUN python -m pip install --no-cache-dir \
    ./packages/relaymd-core \
    ./packages/relaymd-worker

ENTRYPOINT ["python", "-m", "relaymd.worker"]
