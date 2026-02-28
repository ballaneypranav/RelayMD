# RelayMD: Scheduling Policy

The orchestrator scores all idle workers and assigns the highest-scoring one to each queued job. The scoring policy, in priority order:

1. **GPU count** — more GPUs score higher (multiplied by 1000)
2. **Platform** — HPC scores above Salad Cloud at equal GPU count (bonus of 1000)
3. **GPU VRAM** — among workers with equal GPU count and platform, higher VRAM scores higher (H100 > A100 > A6000 > RTX 4090 > A10 > A30)

The requesting worker is only assigned the job if it is the highest-scoring idle worker. This means every worker participates in a fair competition on each poll — no worker gets preferential treatment by polling faster.

Salad Cloud workers are eligible for any job but are assigned only when no HPC workers are available or idle. This ensures cheapest, most capable resources are used first.

The orchestrator schedules a 60-second sbatch submission job. For each configured cluster, if there are queued jobs and no registered (or pending-registration) HPC workers for that cluster, it renders and submits a new SLURM job. It stores the SLURM job ID in the DB as a placeholder worker record to prevent duplicate submissions during the SLURM pending window.

---

## Target HPC Clusters

| Cluster  | Partition   | Wall time limit | Notes                  |
|----------|-------------|-----------------|------------------------|
| clusterA | partitionA | 4h  | Primary dev cluster    |
| clusterA | partitionB | 4h  |                        |
| clusterB | partitionC | 14d | Long-running preferred |
| clusterB | partitionD | 14d |                        |

Each partition is a separate `ClusterConfig` entry in the YAML config. The orchestrator submits to all configured clusters independently. Each cluster uses either a shared-filesystem `.sif` path (`sif_path`) or a registry image reference (`image_uri`) for Apptainer.

The orchestrator runs on the clusterA login node and calls `sbatch` as a direct subprocess (no SSH). clusterB support requires cross-cluster SSH submission, which is not yet implemented.
