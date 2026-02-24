# RelayMD: Architecture & Design

# RelayMD

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

RelayMD has three logical layers: the orchestrator, the workers, and the storage layer. These are connected by a private network and a simple HTTP API.

### Orchestrator

The orchestrator is the only stateful component. It runs as a FastAPI application on a persistent machine — a workstation, a VM, or a cluster login node — backed by a SQLite database. Its responsibilities are:

* Maintaining the canonical state of every job (queued, running, completed, failed) and every worker (registered, idle, running, stale)
* Assigning jobs to workers based on GPU availability and a preference policy
* Detecting stale workers via heartbeat timeouts and re-queuing their jobs
* Proactively submitting new SLURM jobs to HPC clusters via `sbatch` when the queue is idle and work is waiting
* Exposing the REST API that workers and the monitoring UI consume

The orchestrator never touches the simulation directly. It does not know about lambda windows, replica exchange, force fields, or any other scientific detail. A job is just a bundle of files in object storage and a status.

### Workers

A worker is an ephemeral process that runs inside a container — either an Apptainer `.sif` file on HPC or a Docker container on Salad Cloud. The worker client is a small Python package (`relaymd`) that is pip-installed into the container image alongside the MD engine.

On startup, a worker:

1. Fetches secrets from Infisical using a bootstrap token injected at job submission time
2. Joins the private Tailscale network in userspace mode (no root required)
3. Registers with the orchestrator, reporting its hardware (GPU model, count, VRAM, platform)
4. Polls for a job assignment
5. Downloads the input bundle and the latest checkpoint (if one exists) from object storage
6. Launches the MD engine as a subprocess
7. Sends heartbeats to the orchestrator every 60 seconds while the simulation runs
8. On wall-time margin: sends SIGTERM to the subprocess, waits for the checkpoint to be written, uploads it to object storage, and reports the checkpoint path to the orchestrator
9. On clean subprocess exit: reports job completion and exits

The worker has no persistent state. If it dies mid-run, the orchestrator detects the missed heartbeat, marks the job as re-queued, and assigns it to the next available worker. That worker picks up from the last checkpoint as if nothing happened.

### Storage

Object storage is Backblaze B2, chosen for its low cost and its peering relationship with Cloudflare. All writes go directly to B2 via the S3-compatible API. All reads are proxied through a Cloudflare Worker, which eliminates egress fees on downloads — significant over hundreds of checkpoint cycles across many jobs.

The storage layer is implemented as a single shared Python module (`relaymd.storage`) with a dual-endpoint `StorageClient`. The module is imported by both the orchestrator and the worker client. The bucket key layout is fixed by convention:

```
jobs/{job_id}/input/          # Immutable input bundle; uploaded once by the user before job creation
jobs/{job_id}/checkpoints/    # Checkpoint files written by workers; latest is always overwritten
```

Input bundles are never overwritten. Checkpoints are. The orchestrator stores only the key path to the latest checkpoint, not the checkpoint data itself.

### Networking

Workers and the orchestrator communicate over a Tailscale private network (a Tailnet). The orchestrator gets a stable MagicDNS hostname. Workers join the Tailnet on startup using ephemeral auth keys and leave automatically when the container exits.

Tailscale runs in userspace networking mode inside Apptainer containers, which does not require root. This is essential for HPC environments where workers have no elevated privileges. Performance in userspace mode is slightly lower than kernel mode but completely adequate for the control-plane traffic RelayMD generates — the simulation data path goes to object storage, not through Tailscale.

The orchestrator API is not reachable from the public internet. A node must be on the Tailnet to reach it, and a node must have a valid Tailscale ephemeral auth key to join the Tailnet. This provides network-layer authentication without any additional infrastructure.

---

## Job Lifecycle

```
User uploads input bundle to B2
         │
         ▼
User registers job via API (POST /jobs with input_bundle_path)
         │
         ▼
Job enters "queued" state in orchestrator DB
         │
         ▼
Orchestrator submits SLURM job (or user scales Salad replicas)
         │
         ▼
Worker boots → fetches secrets → joins Tailnet → registers with orchestrator
         │
         ▼
Worker polls GET /jobs/assign → receives job_id + input_bundle_path + latest_checkpoint_path
         │
         ▼
Worker downloads input bundle (+ checkpoint if resuming) from B2 via Cloudflare
         │
         ▼
Worker launches MD subprocess; heartbeat thread starts
         │
         ├── Every 60s: POST /workers/{id}/heartbeat
         │
         ├── On checkpoint write: upload to B2, POST /jobs/{id}/checkpoint
         │
         ├── On wall-time margin: SIGTERM → wait → upload → POST /jobs/{id}/checkpoint → exit
         │
         └── On clean exit: POST /jobs/{id}/complete
                   │
                   ▼
              Job marked "completed" in orchestrator DB
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

The orchestrator scores workers and assigns the highest-scoring idle worker to each queued job. The scoring policy, in priority order:

1. **GPU count** — more GPUs score higher. A 4×A100 node scores well above a single A10.
2. **Platform** — HPC scores above Salad Cloud at equal GPU count (lower cost, higher reliability).
3. **GPU VRAM** — among HPC workers with equal GPU count, higher VRAM scores higher (H100 > A100 > A30 > A10).

Salad Cloud workers are eligible for any job but are assigned only when no HPC workers are available. This policy ensures that the cheapest, most capable resources are used first, and paid consumer GPU capacity is consumed only when it is genuinely needed.

The orchestrator also manages SLURM submission proactively: when queued jobs exist and no HPC workers are registered for a given cluster, it calls `sbatch` via SSH to submit a new job. It tracks pending-but-not-yet-registered SLURM jobs to avoid duplicate submissions during the SLURM pending window.

---

## First Use Case: AToM-OpenMM

The first concrete workload RelayMD is designed to run is [AToM-OpenMM](<https://github.com/Gallicchio-Lab/AToM-OpenMM>), an alchemical free energy calculation engine that runs replica exchange across 22 lambda windows on a single multi-GPU node.

From RelayMD's perspective, AToM-OpenMM is an opaque subprocess. The worker launches it via a configurable command template, waits for it to run, and handles checkpointing at the boundaries of each chunk. Replica exchange between lambda windows is entirely internal to the subprocess — the orchestrator never sees individual replicas, only the job as a whole.

AToM-OpenMM supports restart from a checkpoint file, which is the prerequisite for RelayMD's resume-on-any-worker model. The checkpoint captures the full simulation state including the replica ladder and lambda schedule.

A typical AToM job runs for several days of wall time. At a 4-hour SLURM limit per job, this means roughly 15–20 worker handoffs per ligand. RelayMD makes this transparent: progress is tracked by checkpoint, each handoff picks up exactly where the last one left off, and the end result is indistinguishable from an uninterrupted run.

---

## Components

| Component | Description |
| -- | -- |
| `relaymd.orchestrator` | FastAPI app, DB models, scheduling loop, sbatch submission |
| `relaymd.worker` | Bootstrap, main loop, heartbeat thread |
| `relaymd.storage` | Shared dual-endpoint boto3 wrapper |
| `deploy/slurm/` | SLURM job templates for each HPC cluster |
| `deploy/salad/` | Salad Cloud container group configuration |
| `ui/` | Streamlit monitoring dashboard |

---

## Operational Notes

**The orchestrator must run on a persistent machine.** A university workstation that does not sleep, a small VM, or a cluster login node with a systemd user service or tmux session all work. It is not compute-intensive — it is just a database and an HTTP process.

**Workers are cattle, not pets.** Never attempt to rescue a worker that has gone silent. The orchestrator will re-queue its job automatically. Just let it time out.

**Input bundles are immutable.** Once uploaded and registered, the files in `jobs/{job_id}/input/` should never be modified. If you need to change the input, create a new job.

**The bootstrap token is the only secret that needs external injection.** Everything else — B2 credentials, the Tailscale auth key, the RelayMD API token — is fetched from Infisical at runtime using that one token. On HPC, the bootstrap token is injected via SLURM's `--export` environment variable, which is never written to disk and is not visible to other users. On Salad Cloud, it is set in the container environment via the Salad dashboard.