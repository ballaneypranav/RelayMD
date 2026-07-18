# SLURM Worker Template (W-153)

RelayMD orchestrator submits worker jobs by rendering
[job.sbatch.j2](./job.sbatch.j2) and then calling `sbatch`.

## Cluster Configuration

Configure clusters in the RelayMD YAML config under `slurm_cluster_configs`
(see `deploy/config.example.yaml`).

Per-cluster required keys:

- `name`
- `partition`
- `account`
- `gpu_type`
- `gpu_count`
- `worker_images`, mapping each supported profile key to exactly one of:
  - `sif_path` (shared filesystem path to a `.sif`)
  - `image_uri` (registry image such as `ghcr.io/<org>/relaymd-worker-gcncmcmd:sha-abc1234`)

The root configuration declares `worker_image_profiles` and
`default_worker_image`. Jobs persist one profile key, and the scheduler only
provisions workers from a matching `worker_images` source. Cluster-level image
source fields are unsupported; every source belongs under `worker_images`.

Optional keys:

- `wall_time` (template default is `4:00:00`)
- `nodes` (renders `#SBATCH --nodes=<value>`)
- `ntasks` (renders `#SBATCH --ntasks=<value>`)
- `qos` (renders `#SBATCH --qos=<value>`)
- `gres` (overrides default `gpu:<gpu_type>:<gpu_count>`)
- at most one of:
  - `memory` (renders `#SBATCH --mem=<value>`)
  - `memory_per_gpu` (renders `#SBATCH --mem-per-gpu=<value>`)
- `worker_images.<key>.sif_cache_dir` (directory for cached pulled SIFs when using `image_uri`; defaults to `$RELAYMD_SIF_CACHE_DIR` or `~/.apptainer/relaymd-sif-cache`)

## Template Rendering

The orchestrator provides template variables:

- `cluster_name`
- `partition`
- `account`
- `gres`
- `nodes`
- `ntasks`
- `qos`
- `memory`
- `memory_per_gpu`
- `wall_time`
- `apptainer_image` (resolved from `sif_path` or `image_uri`)
- `worker_image_key` (passed to the container as `RELAYMD_WORKER_IMAGE_KEY`)
- `infisical_token`
- `apptainer_docker_username_shell_quoted` / `apptainer_docker_password_shell_quoted` (optional; sourced from host environment variables, not YAML)

The rendered script includes:

- `#SBATCH --partition={{ partition }}`
- `#SBATCH --account={{ account }}`
- `#SBATCH --gres={{ gres }}`
- `#SBATCH --nodes={{ nodes }}` (when configured)
- `#SBATCH --ntasks={{ ntasks }}` (when configured)
- `#SBATCH --qos={{ qos }}` (when configured)
- `#SBATCH --mem={{ memory }}` (when configured)
- `#SBATCH --mem-per-gpu={{ memory_per_gpu }}` (when configured)
- `#SBATCH --time={{ wall_time }}`
- `#SBATCH --signal=TERM@{{ slurm_sigterm_margin_seconds }}`
- `#SBATCH --export=ALL`
- `export INFISICAL_BOOTSTRAP_TOKEN=...`
- `export APPTAINERENV_INFISICAL_TOKEN="${INFISICAL_BOOTSTRAP_TOKEN}"`

For private registry pulls (`image_uri`), set Apptainer auth env vars in the
service env file before startup:

- `APPTAINER_DOCKER_USERNAME`
- `APPTAINER_DOCKER_PASSWORD`

Runtime command includes validated Apptainer flags from `docs/hpc-notes.md`:

```bash
apptainer exec --nv --cleanenv --writable-tmpfs --bind /tmp:/tmp \
  --env RELAYMD_WORKER_IMAGE_KEY=atom-openmm \
  /depot/plow/apps/relaymd/current/relaymd-worker-atom-openmm.sif python -m relaymd.worker

# GCNCMC-MD registry source:
apptainer exec --nv --cleanenv --writable-tmpfs --bind /tmp:/tmp \
  --env RELAYMD_WORKER_IMAGE_KEY=gcncmcmd \
  docker://ghcr.io/<org>/relaymd-worker-gcncmcmd:sha-abc1234 python -m relaymd.worker
```

Use immutable image tags, digests, or versioned SIF paths. A cluster can support
one or both profiles, but it must explicitly map each supported key. Pending and
active worker limits are evaluated per cluster/profile pair.

Runtime env vars are injected by the template (`WORKER_PLATFORM`, heartbeat/checkpoint intervals, and timeout knobs) from orchestrator config defaults.

## Dry-Run Test

Before live submission, render to a file and use SLURM test-only mode:

```bash
sbatch --test-only rendered-job.sbatch
```

This validates scheduler directives and account/partition combinations without
starting a worker.
