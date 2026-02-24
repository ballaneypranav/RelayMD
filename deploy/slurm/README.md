# SLURM Worker Template (W-153)

RelayMD orchestrator submits worker jobs by rendering
[job.sbatch.j2](./job.sbatch.j2) and then calling `sbatch`.

## Cluster Configuration

Copy [clusters.example.toml](./clusters.example.toml) to your real
`clusters.toml` (or equivalent orchestrator config path) and fill in values for
each cluster.

Per-cluster required keys:

- `partition`
- `account`
- `gpu_type`
- `gpu_count`
- `sif_path`

Optional keys:

- `wall_time` (template default is `4:00:00`)

## Template Rendering

The orchestrator provides template variables:

- `cluster_name`
- `partition`
- `account`
- `gpu_type`
- `gpu_count`
- `wall_time`
- `sif_path`
- `infisical_token`

The rendered script includes:

- `#SBATCH --partition={{ partition }}`
- `#SBATCH --account={{ account }}`
- `#SBATCH --gres=gpu:{{ gpu_type }}:{{ gpu_count }}`
- `#SBATCH --time={{ wall_time }}`
- `#SBATCH --export=ALL,INFISICAL_BOOTSTRAP_TOKEN={{ infisical_token }}`

Runtime command includes validated Apptainer flags from `docs/hpc-notes.md`:

```bash
apptainer exec --nv --cleanenv --writable-tmpfs --bind /tmp:/tmp <sif_path> python -m relaymd.worker
```

## Dry-Run Test

Before live submission, render to a file and use SLURM test-only mode:

```bash
sbatch --test-only rendered-job.sbatch
```

This validates scheduler directives and account/partition combinations without
starting a worker.
