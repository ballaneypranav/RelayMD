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
- exactly one of:
  - `sif_path` (shared filesystem path to a `.sif`)
  - `image_uri` (registry image such as `ghcr.io/<org>/relaymd-worker:latest`)

Optional keys:

- `wall_time` (template default is `4:00:00`)
- `nodes` (renders `#SBATCH --nodes=<value>`)
- `ntasks` (renders `#SBATCH --ntasks=<value>`)
- `qos` (renders `#SBATCH --qos=<value>`)
- `gres` (overrides default `gpu:<gpu_type>:<gpu_count>`)
- at most one of:
  - `memory` (renders `#SBATCH --mem=<value>`)
  - `memory_per_gpu` (renders `#SBATCH --mem-per-gpu=<value>`)

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
- `infisical_token`
- `apptainer_docker_username` / `apptainer_docker_password` (optional)

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
- `#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN={{ infisical_token }}`

For private registry pulls (`image_uri`), export Apptainer auth env vars before
`apptainer exec`:

- `APPTAINER_DOCKER_USERNAME`
- `APPTAINER_DOCKER_PASSWORD`
- compatibility aliases: `SINGULARITY_DOCKER_USERNAME` / `SINGULARITY_DOCKER_PASSWORD`

Runtime command includes validated Apptainer flags from `docs/hpc-notes.md`:

```bash
apptainer exec --nv --cleanenv --writable-tmpfs --bind /tmp:/tmp <sif_path> python -m relaymd.worker

# or when using image_uri:
apptainer exec --nv --cleanenv --writable-tmpfs --bind /tmp:/tmp \
  docker://ghcr.io/<org>/relaymd-worker:latest python -m relaymd.worker
```

Runtime env vars are injected by the template (`WORKER_PLATFORM`, heartbeat/checkpoint intervals, and timeout knobs) from orchestrator config defaults.

## Dry-Run Test

Before live submission, render to a file and use SLURM test-only mode:

```bash
sbatch --test-only rendered-job.sbatch
```

This validates scheduler directives and account/partition combinations without
starting a worker.
