# HPC Apptainer + Tailscale Notes

This document captures the cluster runbook and validation checklist for
`W-151`: running RelayMD worker containers as Apptainer `.sif` images with
Tailscale userspace networking on SLURM-managed HPC nodes.

## 1) Pull and Convert from GHCR

Run on a cluster login node:

```bash
export ORG=<org>
export IMAGE="ghcr.io/${ORG}/relaymd-worker:latest"
export SHARED_DIR=/path/to/shared/project/containers
mkdir -p "${SHARED_DIR}"
apptainer pull "${SHARED_DIR}/relaymd.sif" "docker://${IMAGE}"
```

Expected output:
- `relaymd.sif` exists at `${SHARED_DIR}/relaymd.sif`
- file is readable from compute nodes (shared filesystem path)

## 2) Submit Tailscale Userspace Validation Job

Use [test_tailscale.sbatch](/depot/plow/data/pballane/folate-alpha-beta/relaymd/deploy/slurm/test_tailscale.sbatch):

```bash
export TAILSCALE_AUTH_KEY=<ephemeral_auth_key>
export ORCHESTRATOR_HOSTNAME=<orchestrator_magicdns_hostname>
export RELAYMD_SIF_PATH=/path/to/shared/project/containers/relaymd.sif
# Optional, cluster-specific:
# export APPTAINER_FLAGS="--cleanenv --writable-tmpfs --bind /tmp:/tmp"

sbatch deploy/slurm/test_tailscale.sbatch
```

Success criteria:
- job exits `0`
- `tailscale-healthz-<jobid>-<node>.log` contains `{"status":"ok"...}`
- job stdout contains `Tailscale userspace + orchestrator healthz test passed`

## 3) Manual Validation Checklist

Required checks for `Definition of Done`:

1. Node appears in Tailscale admin panel during job execution:
   - expected hostname prefix: `relaymd-test-`
2. `GET /healthz` response from container is `{"status":"ok", ...}`
3. Node disappears from Tailscale admin panel within a few minutes after job
   completion (ephemeral key behavior)

## 4) Cluster-Specific Flags/Notes

Record the exact options needed on your cluster (fill this section after live run):

- Required `apptainer exec` flags:
  - `--cleanenv`
  - `--writable-tmpfs`
  - `--bind /tmp:/tmp`
- Additional required flags:
  - `<none observed yet>`
- Namespace/network caveats:
  - `<fill after first successful run>`
- Filesystem caveats:
  - `<fill after first successful run>`

## 5) Live Run Results

Fill this section after executing on the real HPC cluster:

- Cluster name:
- Login node used:
- Shared `.sif` path:
- SLURM job id:
- Compute node:
- Tailscale admin panel check (appear/disappear):
- `/healthz` response:
- Final status:
