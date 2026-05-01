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
         └── POST /jobs with id={job_id} → job enters "queued" state in orchestrator DB
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
                  ├── checkpoint polling interval:
                  │       bundle `checkpoint_poll_interval_seconds` (if present)
                  │       else worker runtime default (global)
                  │
                  ├── every poll interval: new checkpoint found?
                  │       → upload to B2
                  │       → POST /jobs/{id}/checkpoint
                  │       → if job already terminal: typed 409 conflict (safe to ignore)
                  │
                  ├── on wall-time margin (SIGTERM from SLURM):
                  │       → send SIGTERM to subprocess
                  │       → wait up to 60s for checkpoint newer than pre-shutdown baseline mtime
                  │       → if newer checkpoint exists: upload to B2 + POST /jobs/{id}/checkpoint
                  │       → exit  (orchestrator re-queues automatically)
                  │
                  └── on clean subprocess exit:
                          → POST /jobs/{id}/complete (or /fail)
                          → late callback against terminal state may return typed 409
                          → loop back to POST /jobs/request
```

If the worker dies without reporting:

```
Orchestrator detects stale heartbeat (`last_heartbeat > heartbeat_interval_seconds × heartbeat_timeout_multiplier`, default `60 × 2 = 120s`)
         │
         ▼
Job re-enters "queued" state with latest_checkpoint_path preserved
         │
         ▼
Next available worker resumes from that checkpoint
```

---

## First Use Case: AToM-OpenMM

The first concrete workload RelayMD is designed to run is [AToM-OpenMM](https://github.com/Gallicchio-Lab/AToM-OpenMM), an alchemical free-energy engine that runs replica exchange across multiple lambda windows on a single multi-GPU node.

From RelayMD's perspective, AToM-OpenMM is an opaque subprocess. The worker launches it via a command specified in the input bundle's `relaymd-worker.json` config file, waits for it to run, and handles checkpointing at the boundaries of each chunk. Replica exchange between lambda windows is entirely internal to the subprocess — the orchestrator never sees individual replicas, only the job as a whole.

AToM-OpenMM supports restart from a checkpoint file, which is the prerequisite for RelayMD's resume-on-any-worker model. A typical job runs for several days of wall time. At a 4-hour SLURM limit per job, this means roughly 15–20 worker handoffs per ligand. RelayMD makes this transparent: each handoff picks up exactly where the last one left off.

The input bundle for an AToM job contains all simulation input files plus a `relaymd-worker.json`:

```json
{
  "command": "python run_atom.py --config simulation.json",
  "checkpoint_glob_pattern": "*.chk",
  "checkpoint_poll_interval_seconds": 60
}
```

The `--command` flag on `relaymd submit` can write this file automatically so it does not need to be included in the source directory. When `--command` is used, `--checkpoint-glob` is required.
