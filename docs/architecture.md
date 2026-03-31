# RelayMD: Core Architecture

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
- Proactively submitting new SLURM jobs to HPC clusters via `sbatch` (direct subprocess call — the orchestrator runs on the login node where `sbatch` is in `PATH`) when the queue is idle and work is waiting. This provisioning behavior is configurable via the `strategy` field on each cluster (`reactive`, `continuous`, or `jit_threshold`).
- Exposing the REST API that workers, the CLI, and the monitoring UI consume

The orchestrator never touches the simulation directly. It does not know about lambda windows, replica exchange, force fields, or any other scientific detail. A job is just a bundle of files in object storage and a status.

Background maintenance work (stale worker reap, orphaned requeue, sbatch submission) runs in-process via APScheduler interval jobs.

### Workers

A worker is an ephemeral process that runs inside a container — either an Apptainer `.sif` file on HPC or a Docker container on Salad Cloud. The worker client is a small Python package (`relaymd-worker`) that is pip-installed into the container image alongside the MD engine.

On startup, a worker:

1. Fetches secrets from Infisical using a bootstrap token injected at job submission time
2. Joins the private Tailscale network in userspace mode (no root required)
3. Registers with the orchestrator, reporting its hardware (GPU model, count, VRAM, platform). On HPC, the worker also passes `slurm_job_id` (from `$SLURM_JOB_ID`) in the registration payload. The orchestrator uses this to atomically delete the corresponding placeholder row, so only one worker row exists per SLURM allocation.
4. Polls for a job assignment. If none is available, handles idle state based on `worker_idle_strategy`:
   - `immediate_exit`: Exits cleanly (default).
   - `poll_then_exit`: Sleeps `worker_idle_poll_interval_seconds` and retries, up to `worker_idle_poll_max_seconds` before exiting cleanly.
5. Downloads the input bundle and the latest checkpoint (if one exists) from object storage
6. Launches the MD engine as a subprocess
7. Sends heartbeats to the orchestrator every `worker_heartbeat_interval_seconds` (default 60s) while the worker process is alive (polling + running)
8. On wall-time margin (`slurm_sigterm_margin_seconds`, default 300s via `#SBATCH --signal=TERM@300`): sends SIGTERM to the subprocess, waits for a final checkpoint write, uploads it to object storage, and reports the checkpoint path to the orchestrator — then exits cleanly
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
| `frontend/`        | React operator dashboard built by Vite and served by the orchestrator |

---

## Operational Notes

**The orchestrator must run on a persistent machine.** A cluster login node with a tmux session works. It is not compute-intensive — it is just a database and an HTTP process. On clusterA, use `deploy/tmux/start-orchestrator.sh`.

**Workers are cattle, not pets.** Never attempt to rescue a worker that has gone silent. The orchestrator will re-queue its job automatically when the heartbeat times out. Just let it time out.

**Typed transition conflicts are expected under races.** Late worker callbacks (`checkpoint`, `complete`, `fail`) can receive a typed `409 job_transition_conflict`; this is expected safety behavior, not an incident.

**Input bundles are immutable.** Once uploaded and registered, the files in `jobs/{job_id}/input/` should never be modified. If the input needs to change, create a new job.

**The bootstrap token is the only secret that needs external injection.** Everything else — B2 credentials, the Tailscale auth key, the RelayMD API token — is fetched from Infisical at runtime using that one token. On HPC, the bootstrap token is injected via SLURM's `--export` environment variable. On Salad Cloud, it is set in the container environment via the Salad dashboard.

**The CLI binary is not the worker.** The `relaymd` binary lives on the login node and is used by the operator to submit and manage jobs. The Apptainer `.sif` container is a completely separate artifact that runs on compute nodes. They share library code (`relaymd-models`, `relaymd-storage`) but are independently built and deployed.
