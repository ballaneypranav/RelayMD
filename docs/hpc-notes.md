# HPC Apptainer + Tailscale Notes

This document captures the cluster runbook and validation checklist for
`W-151`: running RelayMD worker containers as Apptainer `.sif` images with
Tailscale userspace networking on SLURM-managed HPC nodes.

## 1) Pull and Convert from GHCR

Run on a cluster login node:

```bash
export ORG=<org>
export RELEASE_DIR=/depot/plow/apps/relaymd/releases/<version>
mkdir -p "${RELEASE_DIR}"

apptainer pull "${RELEASE_DIR}/relaymd-orchestrator.sif" \
  "docker://ghcr.io/${ORG}/relaymd-orchestrator:sha-<shortsha>"
apptainer pull "${RELEASE_DIR}/relaymd-worker.sif" \
  "docker://ghcr.io/${ORG}/relaymd-worker:sha-<shortsha>"
ln -sfn "${RELEASE_DIR}" /depot/plow/apps/relaymd/current
```

Expected output:
- both SIFs exist under `${RELEASE_DIR}`
- file is readable from compute nodes (shared filesystem path)

## 2) Submit Tailscale Userspace Validation Job

Use the `test_tailscale.sbatch` template available in the repo under `deploy/slurm/`:

```bash
export TAILSCALE_AUTH_KEY=<ephemeral_auth_key>
export ORCHESTRATOR_HOSTNAME=<orchestrator_magicdns_hostname>
export RELAYMD_SIF_PATH=/depot/plow/apps/relaymd/current/relaymd-worker.sif
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

## 6) Fakeroot Validation Note

`apptainer build --fakeroot` was probed on this HPC and is not currently a
supported path due missing usable fakeroot/subuid support. RelayMD deployment
uses GHCR-published images plus `apptainer pull` on the login node.
