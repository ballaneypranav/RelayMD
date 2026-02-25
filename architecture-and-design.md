# RelayMD: Architecture & Design

**A distributed orchestration system for long-running molecular dynamics simulations across heterogeneous compute resources.**

---

## Purpose

Computational free energy calculations — particularly alchemical methods like AToM — are among the most valuable and most expensive workloads in computational drug discovery. They require days to weeks of continuous GPU time, but the compute resources available to a researcher are rarely continuous: HPC cluster allocations are fragmented into short jobs, queues are unpredictable, and idle capacity across multiple clusters goes unused because there is no mechanism to exploit it opportunistically.

RelayMD exists to close this gap. It treats a multi-day simulation as a logical job that can be paused, resumed, and migrated across any available GPU — HPC nodes, cloud spot instances, consumer GPU networks — without the simulation itself needing to know anything about the infrastructure. The result is that a simulation makes progress whenever compute is available, rather than only when a specific queue grants it time.

---

## Philosophy

**The simulation is the unit of work, not the compute job.** A SLURM job or a Salad Cloud container is just a vehicle. The logical simulation has its own identity, its own progress, and its own continuity. Infrastructure is fungible.

**Workers are stateless and ephemeral.** A worker knows nothing about what it ran before and nothing about what other workers are doing. It asks for work, does it, reports back, and disappears. All memory lives in the orchestrator. This makes the system trivially fault-tolerant: a dead worker is just an absent reporter, and its work is automatically reassigned.

**No scientific data moves between nodes during a run.** Replicas exchange within a single worker. The only inter-node communication is control traffic — heartbeats, job assignments, checkpoint reports — which is tiny. Simulation data moves only to and from object storage at checkpoint boundaries, and only vertically (worker ↔ storage), never laterally (worker ↔ worker).

**Checkpoints are the source of truth for progress.** A checkpoint written to object storage represents a verified quantum of work. The orchestrator tracks progress by checkpoint, not by time or step count, so the definition of "done" is exact and crash-safe.

**Prefer HPC, fall back gracefully.** HPC clusters are cheaper and offer multi-GPU nodes that run simulations faster. Consumer GPU networks like Salad Cloud offer availability when HPC queues are long. The orchestrator's scheduling policy encodes this preference explicitly: it fills HPC capacity first and routes overflow to Salad.

---

## Architecture

RelayMD has four logical layers: the operator CLI, the orchestrator, the workers, and the storage layer. The CLI and orchestrator both run on the login node. Workers run on compute nodes. All layers communicate through a private Tailscale network and a simple HTTP API.

```
Operator (you, on login node)
        │
        │  relaymd submit / jobs / workers
        ▼
  ┌─────────────┐        HTTP (Tailnet)       ┌──────────────────────┐
  │ Orchestrator│◄────────────────────────────│   Worker (compute    │
  │ (FastAPI +  │                             │   node, Apptainer)   │
  │  SQLite)    │────── sbatch ──────────────►│                      │
  └─────────────┘                             └──────────────────────┘
        │                                              │
        │                                              │
        ▼                                              ▼
  ┌─────────────┐                             ┌──────────────────────┐
  │ Backblaze B2│◄────────────────────────────│ Backblaze B2 (write) │
  │ via         │                             │ Cloudflare (read)    │
  │ Cloudflare  │                             └──────────────────────┘
  └─────────────┘
```

### Operator CLI

The `relaymd` CLI is a self-contained binary installed on the login node (or any machine from which the operator wants to submit jobs). It handles the full job submission workflow in a single command: packing the input directory into a tarball, uploading it to B2, and registering the job with the orchestrator. It also provides commands to list jobs, inspect status, cancel, and re-queue.

The binary is compiled with PyInstaller and distributed via GitHub Releases. It reads its configuration from the same YAML file as the orchestrator (`~/.config/relaymd/config.yaml`). No Python environment is required to run it — it is a single static ELF binary.

The CLI is not present inside the worker container. It is strictly an operator tool for the login node.

### Orchestrator

The orchestrator is the only stateful component. It runs as a FastAPI application on a persistent machine — in practice, a cluster login node — backed by a SQLite database. Its responsibilities are:

- Maintaining the canonical state of every job (queued, assigned, running, completed, failed, cancelled) and every worker (registered, idle, running, stale)
- Validating all in-place job transitions through a central transition service and returning typed `409` conflicts for invalid transitions
- Assigning jobs to workers based on GPU availability and a preference policy
- Detecting stale workers via heartbeat timeouts and re-queuing their jobs
- Proactively submitting new SLURM jobs to HPC clusters via `sbatch` (direct subprocess call — the orchestrator runs on the login node where `sbatch` is in `PATH`) when the queue is idle and work is waiting
- Exposing the REST API that workers, the CLI, and the monitoring UI consume

The orchestrator never touches the simulation directly. It does not know about lambda windows, replica exchange, force fields, or any other scientific detail. A job is just a bundle of files in object storage and a status.

Background maintenance work (stale worker reap, orphaned requeue, sbatch submission) runs in-process via APScheduler interval jobs.

### Workers

A worker is an ephemeral process that runs inside a container — either an Apptainer `.sif` file on HPC or a Docker container on Salad Cloud. The worker client is a small Python package (`relaymd-worker`) that is pip-installed into the container image alongside the MD engine.

On startup, a worker:

1. Fetches secrets from Infisical using a bootstrap token injected at job submission time
2. Joins the private Tailscale network in userspace mode (no root required)
3. Registers with the orchestrator, reporting its hardware (GPU model, count, VRAM, platform)
4. Polls for a job assignment
5. Downloads the input bundle and the latest checkpoint (if one exists) from object storage
6. Launches the MD engine as a subprocess
7. Sends heartbeats to the orchestrator every 60 seconds while the simulation runs
8. On wall-time margin: sends SIGTERM to the subprocess, waits for a final checkpoint write, uploads it to object storage, and reports the checkpoint path to the orchestrator — then exits cleanly
9. On clean subprocess exit: reports job completion and loops back to poll for another job

The worker has no persistent state. If it dies mid-run, the orchestrator detects the missed heartbeat, marks the job as re-queued, and assigns it to the next available worker. That worker picks up from the last checkpoint as if nothing happened.

Internally, the runtime is split into two seams:
- `OrchestratorGateway` (API transport + conflict normalization)
- `JobExecution` (non-blocking subprocess + checkpoint polling)

### Storage

Object storage is Backblaze B2, chosen for its low cost and its peering relationship with Cloudflare. All writes go directly to B2 via the S3-compatible API. All reads are proxied through a Cloudflare Worker, which eliminates egress fees on downloads — significant over hundreds of checkpoint cycles across many jobs.

The storage layer is implemented as a shared Python module (`relaymd-storage`) with a dual-endpoint `StorageClient`. It is imported by the orchestrator, the worker, and the CLI. The bucket key layout is fixed by convention:

```
jobs/{job_id}/input/bundle.tar.gz   # Immutable input bundle; uploaded once by the CLI
jobs/{job_id}/checkpoints/latest    # Latest checkpoint; overwritten on every checkpoint cycle
```

Input bundles are never overwritten. The orchestrator stores only the key path to the latest checkpoint, not the checkpoint data itself.

### Networking

Workers and the orchestrator communicate over a Tailscale private network (a Tailnet). The orchestrator gets a stable MagicDNS hostname. Workers join the Tailnet on startup using ephemeral auth keys and leave automatically when the container exits.

Tailscale runs in userspace networking mode inside Apptainer containers, which does not require root. This is essential for HPC environments where workers have no elevated privileges. Performance in userspace mode is slightly lower than kernel mode but completely adequate for the control-plane traffic RelayMD generates — the simulation data path goes to object storage, not through Tailscale.

The orchestrator API is not reachable from the public internet. A node must be on the Tailnet to reach it, and a node must have a valid ephemeral auth key to join. This provides network-layer authentication without any additional infrastructure.

---

## Job Lifecycle

```
Operator prepares simulation input directory
         │
         ▼
relaymd submit ./inputs/ --title "lig42-eq1" --command "python run_atom.py"
         │
         ├── packs directory into bundle.tar.gz
         ├── uploads to B2 at jobs/{uuid}/input/bundle.tar.gz
         └── POST /jobs → job enters "queued" state in orchestrator DB
                  │
                  ▼
         Orchestrator sbatch loop fires (every 60s)
         Sees queued job, no active HPC workers for cluster
                  │
                  ▼
         sbatch renders job.sbatch.j2 and calls sbatch directly
                  │
                  ▼
         Worker boots on compute node
         → fetches secrets from Infisical
         → joins Tailnet
         → registers with orchestrator (POST /workers/register)
                  │
                  ▼
         Worker polls POST /jobs/request
         → receives job_id + input_bundle_path + latest_checkpoint_path
                  │
                  ▼
         Worker downloads input bundle (+ checkpoint if resuming) from B2
                  │
                  ▼
         Worker launches MD subprocess; heartbeat thread starts
                  │
                  ├── every 60s: POST /workers/{id}/heartbeat
                  │
                  ├── every 5min (poll): new checkpoint found?
                  │       → upload to B2
                  │       → POST /jobs/{id}/checkpoint
                  │       → if job already terminal: typed 409 conflict (safe to ignore)
                  │
                  ├── on wall-time margin (SIGTERM from SLURM):
                  │       → send SIGTERM to subprocess
                  │       → wait up to 60s for final checkpoint write
                  │       → upload checkpoint to B2
                  │       → POST /jobs/{id}/checkpoint
                  │       → exit  (orchestrator re-queues automatically)
                  │
                  └── on clean subprocess exit:
                          → POST /jobs/{id}/complete (or /fail)
                          → late callback against terminal state may return typed 409
                          → loop back to POST /jobs/request
```

If the worker dies without reporting:

```
Orchestrator detects stale heartbeat (last_heartbeat > 2× interval)
         │
         ▼
Job re-enters "queued" state with latest_checkpoint_path preserved
         │
         ▼
Next available worker resumes from that checkpoint
```

---

## Scheduling Policy

The orchestrator scores all idle workers and assigns the highest-scoring one to each queued job. The scoring policy, in priority order:

1. **GPU count** — more GPUs score higher (multiplied by 1000)
2. **Platform** — HPC scores above Salad Cloud at equal GPU count (bonus of 1000)
3. **GPU VRAM** — among workers with equal GPU count and platform, higher VRAM scores higher (H100 > A100 > A6000 > RTX 4090 > A10 > A30)

The requesting worker is only assigned the job if it is the highest-scoring idle worker. This means every worker participates in a fair competition on each poll — no worker gets preferential treatment by polling faster.

Salad Cloud workers are eligible for any job but are assigned only when no HPC workers are available or idle. This ensures cheapest, most capable resources are used first.

The orchestrator schedules a 60-second sbatch submission job. For each configured cluster, if there are queued jobs and no registered (or pending-registration) HPC workers for that cluster, it renders and submits a new SLURM job. It stores the SLURM job ID in the DB as a placeholder worker record to prevent duplicate submissions during the SLURM pending window.

---

## First Use Case: AToM-OpenMM

The first concrete workload RelayMD is designed to run is [AToM-OpenMM](https://github.com/Gallicchio-Lab/AToM-OpenMM), an alchemical free-energy engine that runs replica exchange across multiple lambda windows on a single multi-GPU node.

From RelayMD's perspective, AToM-OpenMM is an opaque subprocess. The worker launches it via a command specified in the input bundle's `relaymd-worker.json` config file, waits for it to run, and handles checkpointing at the boundaries of each chunk. Replica exchange between lambda windows is entirely internal to the subprocess — the orchestrator never sees individual replicas, only the job as a whole.

AToM-OpenMM supports restart from a checkpoint file, which is the prerequisite for RelayMD's resume-on-any-worker model. A typical job runs for several days of wall time. At a 4-hour SLURM limit per job, this means roughly 15–20 worker handoffs per ligand. RelayMD makes this transparent: each handoff picks up exactly where the last one left off.

The input bundle for an AToM job contains all simulation input files plus a `relaymd-worker.json`:

```json
{
  "command": "python run_atom.py --config simulation.json",
  "checkpoint_glob_pattern": "*.chk"
}
```

The `--command` flag on `relaymd submit` can write this file automatically so it does not need to be included in the source directory.

---

## Target HPC Clusters

| Cluster  | Partition   | Wall time limit | Notes                  |
|----------|-------------|-----------------|------------------------|
| clusterA | partitionA | 4h  | Primary dev cluster    |
| clusterA | partitionB | 4h  |                        |
| clusterB | partitionC | 14d | Long-running preferred |
| clusterB | partitionD | 14d |                        |

Each partition is a separate `ClusterConfig` entry in the YAML config. The orchestrator submits to all configured clusters independently. Each cluster requires its own `.sif` path on its own shared filesystem.

The orchestrator runs on the clusterA login node and calls `sbatch` as a direct subprocess (no SSH). clusterB support requires cross-cluster SSH submission, which is not yet implemented.

---

## Components

| Component          | Description                                                          |
|--------------------|----------------------------------------------------------------------|
| `relaymd-cli`      | Operator CLI: submit, list, cancel, requeue. Compiled to a binary.  |
| `relaymd-orchestrator` | FastAPI app, DB models, scheduling loops, sbatch submission     |
| `relaymd-worker`   | Bootstrap, main loop, heartbeat thread; runs inside container        |
| `relaymd-storage`  | Shared dual-endpoint boto3 wrapper; used by all three above          |
| `relaymd-models`   | Shared Pydantic/SQLModel types; used by all packages                 |
| `orchestrator/services` | Transition/state authority plus assignment, lifecycle, autoscaling, and provisioning services |
| `worker/context-gateway-execution` | `WorkerContext`, `OrchestratorGateway`, and `JobExecution` seams for procedural worker loop |
| `cli/context-services` | Shared CLI context plus jobs/workers/submit service adapters |
| `deploy/slurm/`    | SLURM job templates and cluster config                               |
| `deploy/salad/`    | Salad Cloud container group configuration                            |
| `ui/`              | Streamlit monitoring dashboard                                       |

---

## Operational Notes

**The orchestrator must run on a persistent machine.** A cluster login node with a tmux session works. It is not compute-intensive — it is just a database and an HTTP process. On clusterA, use `deploy/tmux/start-orchestrator.sh`.

**Workers are cattle, not pets.** Never attempt to rescue a worker that has gone silent. The orchestrator will re-queue its job automatically when the heartbeat times out. Just let it time out.

**Typed transition conflicts are expected under races.** Late worker callbacks (`checkpoint`, `complete`, `fail`) can receive a typed `409 job_transition_conflict`; this is expected safety behavior, not an incident.

**Input bundles are immutable.** Once uploaded and registered, the files in `jobs/{job_id}/input/` should never be modified. If the input needs to change, create a new job.

**The bootstrap token is the only secret that needs external injection.** Everything else — B2 credentials, the Tailscale auth key, the RelayMD API token — is fetched from Infisical at runtime using that one token. On HPC, the bootstrap token is injected via SLURM's `--export` environment variable. On Salad Cloud, it is set in the container environment via the Salad dashboard.

**The CLI binary is not the worker.** The `relaymd` binary lives on the login node and is used by the operator to submit and manage jobs. The Apptainer `.sif` container is a completely separate artifact that runs on compute nodes. They share library code (`relaymd-models`, `relaymd-storage`) but are independently built and deployed.

---

## Open Items

- **AToM-OpenMM checkpoint glob pattern** — what files does AToM actually write? Finalize during end-to-end testing.
- **Salad GPU model strings** — the VRAM tier lookup table needs to be populated with exact `nvidia-smi` model name strings from real Salad nodes.
- **clusterB cross-cluster sbatch** — the orchestrator currently calls `sbatch` as a direct subprocess and must run on the same login node as the target cluster. Submitting to clusterB from a clusterA-hosted orchestrator requires SSH-based submission, which is not yet implemented.

---
