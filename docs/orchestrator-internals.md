# RelayMD: Orchestrator Internals

## Web Framework

FastAPI, async throughout. All route handlers are `async def`. Database calls use an `AsyncSession`. No `run_in_executor` wrappers needed — the orchestrator is entirely I/O-bound.

## Database

SQLite via SQLModel (which wraps SQLAlchemy 2.0 + Pydantic). SQLModel unifies the ORM model and Pydantic schema into a single class definition, eliminating the boilerplate of separate `JobDB` / `JobResponse` classes. Migrations via Alembic.

## Networking Constraint: All Communication is Worker-Initiated

**Salad Cloud blocks all inbound traffic to containers.** This is a hard platform constraint.

The rule: the orchestrator never initiates a connection to a worker. Every interaction is a worker making an outbound HTTP request to the orchestrator. The worker lifecycle is designed so this constraint never requires a workaround — the orchestrator controls worker behaviour entirely through job assignment responses, not push signals.

## Configuration

`pydantic-settings` with `YamlConfigSettingsSource`. Config is loaded from a YAML file (path from `RELAYMD_CONFIG` env var, default `~/.config/relaymd/config.yaml`). Env vars override YAML for secrets so that `api_token` and `infisical_token` never need to appear in a file on disk.

A missing YAML file is non-fatal — the orchestrator starts with defaults and logs a warning. The reference config is `deploy/config.example.yaml`.

## Scheduling Loops

Three APScheduler interval jobs are registered from FastAPI `lifespan` using an in-memory `AsyncIOScheduler`:

1. **`stale_worker_reaper_job`** — every `stale_worker_reaper_interval_seconds` (default 60s); marks workers stale if `last_heartbeat > heartbeat_interval_seconds × heartbeat_timeout_multiplier`; re-queues their jobs; calls Salad autoscaling.
2. **`orphaned_job_requeue_once`** — every `orphaned_job_requeue_interval_seconds` (default 60s); handles jobs that reached `assigned` state but whose worker never registered (e.g. SLURM job failed to boot).
3. **`sbatch_submission_job`** — every `sbatch_submission_interval_seconds` (default 60s); for each `ClusterConfig`, proceeds in two steps:
   - **Dead-placeholder reap**: queries all placeholder workers (those with `slurm_job_id` containing `:`), calls `squeue --jobs <id,...>`, and deletes any whose SLURM job is no longer alive. This reclaims the `max_pending_jobs` slot so the next submission cycle can proceed. Errors from `squeue` (e.g. on non-HPC environments) are swallowed and never crash the scheduler.
   - **New submission**: if there are queued jobs and no active/pending HPC workers for that cluster, renders the Jinja2 sbatch template and calls `sbatch --parsable` as a direct subprocess. Stores the SLURM job ID in the DB as a placeholder worker record (`slurm_job_id = "<cluster>:<id>"`) to prevent duplicate submissions during the SLURM pending window.

Scheduler settings: `coalesce=True`, `max_instances=1`, no persistent job store.

## sbatch Submission

Direct subprocess call — no SSH, no paramiko. The orchestrator runs on the login node where `sbatch` is in `PATH`. Submission is:

```python
result = await asyncio.create_subprocess_exec(
    "sbatch", "--parsable", rendered_script_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**Current limitation:** the orchestrator must run on the same login node as the target cluster. Cross-cluster submission (e.g. submitting to clusterB from a clusterA-hosted orchestrator) requires SSH and is not yet implemented.

## Placeholder Worker Lifecycle

When `sbatch` succeeds, the orchestrator inserts a **placeholder** `Worker` row with:

- `platform = hpc`
- `slurm_job_id = "<cluster_name>:<slurm_job_id>"` (the colon is the sentinel)
- `vram_gb = 0` (unknown until the real worker registers)
- `last_heartbeat = now`

The placeholder is visible in the UI with `status = provisioning`. It is **never reaped by the stale-worker reaper** (which explicitly skips rows whose `slurm_job_id` contains `:`), and it is **never assigned jobs** (the assignment query requires `slurm_job_id IS NULL`).

The placeholder is cleaned up by one of two paths:

1. **Happy path** — the SLURM job starts and the worker process calls `POST /workers/register` with `slurm_job_id` set to `$SLURM_JOB_ID`. `register_worker` finds the matching placeholder (by suffix `":<id>"`) and deletes it atomically before committing the real worker row. The real worker has `slurm_job_id = NULL` and a live heartbeat.

2. **Dead-job path** — the `sbatch_submission_job` scheduler calls `reap_dead_slurm_placeholders` before each submission cycle. It calls `squeue --jobs <id1,id2,...> --noheader --format=%i` and deletes any placeholder whose job ID is no longer returned by squeue (job failed, timed out, or was cancelled before starting).
