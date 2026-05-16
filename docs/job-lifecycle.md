# RelayMD: Job Lifecycle

## Lifecycle Flow

```
Operator prepares simulation input directory
         │
         ▼
relaymd submit ./inputs/ --title "lig42-eq1" --command "python run_atom.py"
         │
         ├── packs directory into bundle.tar.gz
         ├── generates canonical job_id UUID once
         ├── uploads to B2 at jobs/{job_id}/input/bundle.tar.gz
         └── POST /jobs with id={job_id} (+ optional preferred_clusters/comment)
             → job enters "queued" state in orchestrator DB
                  │
                  ▼
         Orchestrator sbatch loop fires (every 60s)
         Sees queued job compatible with cluster affinity, no active HPC workers for cluster
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
                  ├── checkpoint polling interval:
                  │       bundle `checkpoint_poll_interval_seconds` (if present)
                  │       else worker runtime default (global)
                  │
                  ├── every poll interval: new checkpoint found?
                  │       → upload to B2
                  │       → POST /jobs/{id}/checkpoint
                  │       → if job already terminal: typed 409 conflict (safe to ignore)
                  │
                  ├── before allocation deadline (default 600s margin):
                  │       → POST /jobs/{id}/handoff/start (running → handoff)
                  │       → stop subprocess gracefully
                  │       → run final non-destructive checkpoint manifest cycle
                  │       → POST /jobs/{id}/handoff/complete (handoff → queued)
                  │       → deregister worker and exit 0
                  │
                  ├── fallback if proactive handoff is unavailable/late (SIGTERM from SLURM):
                  │       → send SIGTERM to subprocess
                  │       → wait up to 60s for checkpoint newer than pre-shutdown baseline mtime
                  │       → if newer checkpoint exists: upload to B2 + POST /jobs/{id}/checkpoint
                  │       → exit (stale-worker cleanup may requeue)
                  │
                  └── on clean subprocess exit:
                          → POST /jobs/{id}/complete (or /fail)
                          → late callback against terminal state may return typed 409
                          → loop back to POST /jobs/request
```

If the worker dies without reporting:

```
Orchestrator detects stale API heartbeat (`last_heartbeat > heartbeat_interval_seconds × heartbeat_timeout_multiplier`, default `60 × 2 = 120s`)
         │
         ▼
Read storage-backed liveness `jobs/<job_id>/checkpoints/status.json`
and (for HPC workers) query SLURM allocation state
         │
         ├── `status.json` fresh OR SLURM allocation still alive:
         │       keep job in active segment (`running` or `handoff`)
         │       and keep worker/job assignment
         │
         └── provider gone (or no provider and storage status stale):
                 requeue job with latest_checkpoint_path preserved
                 next available worker resumes from that checkpoint
```

If a queued job has affinity that cannot currently run, status remains `queued`
and `queue_blocked_reason` is set:
- `no_enabled_pinned_clusters`: all pinned clusters are currently disabled
- `no_matching_pinned_clusters`: pinned cluster names no longer match runtime config

---

## First Use Case: AToM-OpenMM

The first concrete workload RelayMD is designed to run is [AToM-OpenMM](https://github.com/Gallicchio-Lab/AToM-OpenMM), an alchemical free-energy engine that runs replica exchange across multiple lambda windows on a single multi-GPU node.

From RelayMD's perspective, AToM-OpenMM is an opaque subprocess. The worker launches it via a command specified in the input bundle's `relaymd-worker.json` config file, waits for it to run, and handles checkpointing at the boundaries of each chunk. Replica exchange between lambda windows is entirely internal to the subprocess — the orchestrator never sees individual replicas, only the job as a whole.

AToM-OpenMM supports restart from a checkpoint file, which is the prerequisite for RelayMD's resume-on-any-worker model. A typical job runs for several days of wall time. At a 4-hour SLURM limit per job, this means roughly 15–20 worker handoffs per ligand. RelayMD makes this transparent: each handoff picks up exactly where the last one left off.

The input bundle for an AToM job contains all simulation input files plus a `relaymd-worker.json`:

```json
{
  "command": "python run_atom.py --config simulation.json",
  "checkpoint_watch_paths": ["*.chk"],
  "checkpoint_poll_interval_seconds": 60,
  "progress_glob_pattern": ["progress", "r*/job.out"],
  "startup_progress_timeout_seconds": 900,
  "progress_timeout_seconds": 1800,
  "fatal_log_path": "production.log",
  "fatal_log_patterns": ["Traceback", "CUDA_ERROR", "Segmentation fault"]
}
```

The `--command` flag on `relaymd submit` can write this file automatically so it does not need to be included in the source directory. When `--command` is used, `--checkpoint-glob` is required.

Progress and fatal-log supervision are opt-in bundle settings. They let the
worker fail a stuck payload even when the top-level wrapper process is still
alive. The worker remains domain-neutral: AToM-specific file names live in the
generated bundle config, not in RelayMD code.
