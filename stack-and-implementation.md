# RelayMD: Implementation Decisions & Stack Reference

This document records all concrete framework and tooling decisions for the RelayMD implementation. It is the authoritative reference when starting any issue. If a decision here conflicts with an issue description, this document wins — update the issue.

---

## Guiding Principles

**Apptainer-first.** The worker runs inside an Apptainer `.sif` container. All Python dependencies — including the MD engine and the `relaymd-worker` package — must be installed inside the image. Do not rely on the host environment for anything.

**No conda environments.** Conda adds significant image size and slow solve times. Use pip inside the container image. The base image should provide a suitable Python (3.11+) directly.

**uv for out-of-container installs.** The orchestrator runs on the login node outside any container. Use `uv` — not pip, not conda. The orchestrator's dependencies are managed with a `uv` lockfile committed to the repo.

**Pydantic everywhere.** All structured data — API request/response bodies, config objects, DB models, inter-component messages — should be typed with Pydantic. If you are writing a dict with string keys to pass data between functions, use a Pydantic model instead.

**One binary for the operator.** The `relaymd` CLI is compiled to a self-contained ELF binary with PyInstaller and distributed via GitHub Releases. No Python environment is required on the machine that submits jobs.

---

## Language & Runtime

| Decision                       | Choice                      | Rationale                                               |
|-------------------------------|-----------------------------|---------------------------------------------------------|
| Language                       | Python 3.11+                | Required by alchemical MD workloads; modern typing        |
| Package manager (login node)   | `uv`                        | Fast, reproducible, lockfile-based                      |
| Package manager (container)    | pip inside Apptainer/Docker | No conda; uv can also be used in the Dockerfile         |
| CLI distribution               | PyInstaller single binary   | No Python env required on HPC login node                |
| Python typing                  | strict Pydantic throughout  | See guiding principle above                             |

---

## Repository Layout

```
relaymd/
├── src/
│   └── relaymd/
│       ├── cli/                # Operator CLI commands
│       └── orchestrator/       # FastAPI app, DB, scheduler, sbatch
├── packages/
│   ├── relaymd-core/          # Shared models + storage only
│   │   └── src/relaymd/
│   │       ├── models/
│   │       └── storage/
│   └── relaymd-worker/        # Worker bootstrap, main loop, heartbeat
├── deploy/
│   ├── slurm/                 # SLURM .sbatch.j2 templates + cluster configs
│   ├── salad/                 # Salad Cloud container group config
│   ├── tmux/                  # tmux launcher script
│   └── config.example.yaml    # Canonical reference config for orchestrator + CLI
├── docs/
│   ├── api-schema.md
│   ├── cli.md                 # CLI install and usage guide
│   ├── deployment.md          # Orchestrator deployment guide
│   ├── hpc-notes.md           # Apptainer + Tailscale runbook
│   └── storage-layout.md
├── ui/                        # Streamlit monitoring dashboard
├── Dockerfile                 # Worker container image
└── pyproject.toml             # Root relaymd package + workspace config
```

`relaymd-core` is the shared dependency layer: it carries only `relaymd.models` + `relaymd.storage`. The worker container installs `relaymd-core` + `relaymd-worker` only; it does not install `relaymd` (and therefore does not pull FastAPI, uvicorn, alembic, or typer). A `uv` workspace at the repo root manages these three packages with one lockfile.

---

## Networking Constraint: All Communication is Worker-Initiated

**Salad Cloud blocks all inbound traffic to containers.** This is a hard platform constraint.

The rule: the orchestrator never initiates a connection to a worker. Every interaction is a worker making an outbound HTTP request to the orchestrator. The worker lifecycle is designed so this constraint never requires a workaround — the orchestrator controls worker behaviour entirely through job assignment responses, not push signals.

---

## Worker Lifecycle

```
worker boots → fetches secrets → joins Tailnet → registers with orchestrator
    │
    ▼
POST /jobs/request
    ├── response: job assigned
    │       │
    │       ▼
    │   download input bundle + latest checkpoint from B2 via Cloudflare
    │       │
    │       ▼
    │   launch MD subprocess
    │       │
    │       ├── every 60s: POST /workers/{id}/heartbeat
    │       ├── every 5min (poll): new checkpoint? → upload to B2
    │       │                                      → POST /jobs/{id}/checkpoint
    │       │
    │       ├── on SIGTERM (wall time / Salad shutdown):
    │       │       → SIGTERM to subprocess → wait → upload checkpoint
    │       │       → POST /jobs/{id}/checkpoint → exit
    │       │       (orchestrator re-queues automatically)
    │       │
    │       └── on clean subprocess exit:
    │               → POST /jobs/{id}/complete
    │               → loop back to POST /jobs/request
    │
    └── response: no_job_available → worker exits cleanly
```

A worker loops back to request another job immediately after completing one. This means a long-running simulation can be served by the same worker container across multiple wall-time allocations if time permits.

---

## Orchestrator Stack

### Web Framework

FastAPI, async throughout. All route handlers are `async def`. Database calls use an `AsyncSession`. No `run_in_executor` wrappers needed — the orchestrator is entirely I/O-bound.

### Database

SQLite via SQLModel (which wraps SQLAlchemy 2.0 + Pydantic). SQLModel unifies the ORM model and Pydantic schema into a single class definition, eliminating the boilerplate of separate `JobDB` / `JobResponse` classes. Migrations via Alembic.

### Configuration

`pydantic-settings` with `YamlConfigSettingsSource`. Config is loaded from a YAML file (path from `RELAYMD_CONFIG` env var, default `~/.config/relaymd/config.yaml`). Env vars override YAML for secrets so that `api_token` and `infisical_token` never need to appear in a file on disk.

A missing YAML file is non-fatal — the orchestrator starts with defaults and logs a warning. The reference config is `deploy/config.example.yaml`.

```yaml
# Example ~/.config/relaymd/config.yaml
database_url: sqlite+aiosqlite:////home/USER/relaymd/relaymd.db
api_token: change-me          # or set RELAYMD_API_TOKEN env var
infisical_token: ""           # or set INFISICAL_TOKEN env var
heartbeat_timeout_multiplier: 2.0

slurm_cluster_configs:
  - name: clusterA-partitionA
    partition: partitionA
    account: my-lab-account
    gpu_type: gpuTypeA
    gpu_count: 1
    sif_path: /depot/mygroup/containers/relaymd.sif
    wall_time: "4:00:00"
    max_pending_jobs: 1

  - name: clusterA-partitionB
    partition: partitionB
    account: my-lab-account
    gpu_type: gpuTypeB
    gpu_count: 1
    sif_path: /depot/mygroup/containers/relaymd.sif
    wall_time: "4:00:00"

relaymd_env: production
relaymd_log_level: INFO
relaymd_log_format: auto

# CLI settings (used by relaymd binary, ignored by orchestrator)
orchestrator_url: http://localhost:8000
b2_endpoint_url: https://s3.us-west-000.backblazeb2.com
b2_bucket_name: relaymd-bucket
b2_access_key_id: ""          # or set B2_ACCESS_KEY_ID env var
b2_secret_access_key: ""      # or set B2_SECRET_ACCESS_KEY env var
```

### Scheduling Loops

Three asyncio background tasks launched from the FastAPI `lifespan`:

1. **`stale_worker_reaper_loop`** — every 30s; marks workers stale if `last_heartbeat > heartbeat_interval × timeout_multiplier`; re-queues their jobs; calls Salad autoscaling.
2. **`orphaned_job_requeue_loop`** — handles jobs that reached `assigned` state but whose worker never registered (e.g. SLURM job failed to boot).
3. **`sbatch_submission_loop`** — every 60s; for each `ClusterConfig`, if there are queued jobs and no active/pending HPC workers for that cluster, renders the Jinja2 sbatch template and calls `sbatch --parsable` as a direct subprocess. Stores the SLURM job ID in the DB as a placeholder worker record to prevent duplicate submissions.

No APScheduler. No separate process. No cron.

### sbatch Submission

Direct subprocess call — no SSH, no paramiko. The orchestrator runs on the login node where `sbatch` is in `PATH`. Submission is:

```python
result = await asyncio.create_subprocess_exec(
    "sbatch", "--parsable", rendered_script_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**Current limitation:** the orchestrator must run on the same login node as the target cluster. Cross-cluster submission (e.g. submitting to clusterB from a clusterA-hosted orchestrator) requires SSH and is not yet implemented.

---

## Worker Stack

### Packaging

`relaymd-worker` is a pip-installable package installed inside the Apptainer/Docker image at build time. It is not installed on the host. The worker entrypoint is `python -m relaymd.worker` (also registered as a console script `relaymd-worker` inside the container).

### Configuration

`pydantic-settings` (`BaseSettings`) with env vars injected at container launch. The bootstrap token is the only value that needs external injection:

```python
class WorkerSettings(BaseSettings):
    infisical_token: str         # bootstrap token — only external injection needed
    platform: Literal["hpc", "salad"] = "hpc"
    wall_time_limit_seconds: int = 14400    # 4 hours
    wall_time_margin_seconds: int = 300     # SIGTERM 5 min before wall time
    heartbeat_interval_seconds: int = 60
    checkpoint_poll_interval_seconds: int = 300
```

### Secret Bootstrap

The bootstrap token is injected via SLURM's `--export` env var (never written to disk) or the Salad dashboard environment. From it, Infisical provides all other secrets: B2 credentials, the Tailscale ephemeral auth key, the orchestrator API token.

### Tailscale

`tailscale` binary invoked as a subprocess. The worker calls:

```
tailscale up --tun=userspace-networking --authkey=<key> --hostname=relaymd-worker-<worker_id>
```

No Python SDK — the binary is included in the container image. Userspace networking requires no root, which is essential for HPC.

### GPU Detection

`pynvml` (NVIDIA Python bindings for NVML). Used at startup to detect GPU count, model name, and VRAM. Falls back gracefully if no GPU is present (for local testing).

### Heartbeat Thread

A `threading.Thread` (daemon=True). The main loop is synchronous (it blocks on a subprocess). The heartbeat runs in a separate OS thread. A `threading.Event` stops it cleanly when the main loop exits.

---

## Operator CLI Stack

### Package

The operator CLI now lives in the root `relaymd` package (`src/relaymd/cli`). It is **not** installed inside the worker container — it is strictly a login-node tool.

### Distribution

PyInstaller compiles the CLI and all its dependencies (including the embedded CPython interpreter) into a single self-contained ELF binary. The binary is built on `ubuntu-22.04` (glibc 2.35) in CI for broad HPC compatibility and attached to the rolling GitHub Release tag `latest` automatically on every push to `main`.

One-line install on any cluster:

```bash
curl -L https://github.com/<org>/relaymd/releases/latest/download/relaymd-linux-x86_64 \
  -o ~/bin/relaymd && chmod +x ~/bin/relaymd
```

### Configuration

`CliSettings` reads from the same YAML file as `OrchestratorSettings`. It uses `extra="ignore"` so each settings class only picks up the fields it needs.

### Commands

```
relaymd submit <input-dir> --title <n> [--command <cmd>] [--checkpoint-glob <pat>]
relaymd jobs list
relaymd jobs status <job-id>
relaymd jobs cancel <job-id> [--force]
relaymd jobs requeue <job-id>
relaymd workers list
```

`submit` packs the directory into a `.tar.gz`, uploads to B2, and registers the job in one step. If `--command` is provided, it writes `relaymd-worker.json` into the directory before packing. If `--command` is absent, the directory must already contain a `relaymd-worker.json` or `relaymd-worker.toml`.

---

## Checkpoint Strategy

Filesystem polling every 5 minutes. The worker polls the simulation working directory for a file matching the `checkpoint_glob_pattern` from `relaymd-worker.json`. When a newer one is found, it uploads to B2 and reports immediately.

On wall-time margin (default 5 min before SLURM kills the job), the worker sends SIGTERM to the subprocess, waits up to 60 seconds for a final checkpoint write, uploads, and exits. Worst-case checkpoint loss on a crash is 5 minutes.

The exact glob pattern for AToM-OpenMM checkpoints is to be confirmed during end-to-end testing.

---

## Input Bundle Format

The input bundle is a `.tar.gz` archive containing all simulation input files plus a mandatory config file:

```
relaymd-worker.json   (or .toml)
  └── command: "python run_atom.py --config simulation.json"
  └── checkpoint_glob_pattern: "*.chk"
```

The archive root must be flat — no leading path component. The worker extracts it to a temp directory and runs the command from within that directory.

---

## Storage Module

`boto3` with the S3-compatible Backblaze B2 API for writes. Reads are proxied through the Cloudflare Worker URL. The `StorageClient` exposes:

- `upload_file(local_path, b2_key)`
- `download_file(b2_key, local_path)`
- `list_keys(prefix)`

Endpoint selection is automatic by operation type. Used by the orchestrator, worker, and CLI.

---

## Shared Data Models

All API request/response models live in `relaymd-core` under `relaymd.models`, shared by `relaymd` and `relaymd-worker`. If a field changes, it changes in one place and all consumers break loudly at import time rather than silently at runtime.

---

## Logging

`structlog` with JSON output in production, `ConsoleRenderer` in development (detected via `RELAYMD_ENV=development`). Renderer is `orjson` for performance. All log statements use keyword arguments — no f-string messages.

```python
log.info("checkpoint_uploaded", job_id=str(job_id), b2_key=key, size_bytes=size)
```

Both the orchestrator and worker have a `logging.py` module that configures structlog once on startup and exposes `get_logger(name)`.

---

## Testing

| Layer              | Framework                      | Notes                                      |
|--------------------|--------------------------------|--------------------------------------------|
| Orchestrator API   | `pytest` + `httpx AsyncClient` | In-memory SQLite DB per test               |
| Worker logic       | `pytest` + `unittest.mock`     | Mock Infisical, B2, subprocess             |
| Storage module     | `pytest` + `moto`              | `moto` mocks the S3/B2 API locally        |
| Scheduling loops   | `pytest` + `freezegun`         | Freeze time to test stale worker detection |
| CLI commands       | `pytest` + `unittest.mock`     | Mock StorageClient and httpx               |
| Config loading     | `pytest` + `tmp_path`          | Write YAML to temp dir, assert round-trip  |

---

## Container Registry

GHCR (GitHub Container Registry). Images tagged as `ghcr.io/<org>/relaymd-worker:<tag>`. Free for public repositories, no rate limits, integrates with GitHub Actions CI.

---

## Deployment

### Orchestrator (clusterA login node)

```bash
git clone https://github.com/<org>/relaymd.git ~/relaymd
cd ~/relaymd
uv sync
cp deploy/config.example.yaml ~/.config/relaymd/config.yaml
# edit config.yaml
./deploy/tmux/start-orchestrator.sh
```

### CLI binary (login node or laptop)

```bash
curl -L https://github.com/<org>/relaymd/releases/latest/download/relaymd-linux-x86_64 \
  -o ~/bin/relaymd && chmod +x ~/bin/relaymd
# reads ~/.config/relaymd/config.yaml automatically
```

### Worker container (built in CI, used by SLURM)

```bash
# on login node, one-time pull and convert
apptainer pull /depot/mygroup/containers/relaymd.sif \
  docker://ghcr.io/<org>/relaymd-worker:latest
```

The `.sif` path goes into `sif_path` in the YAML config. The orchestrator references it in every rendered sbatch script.

---

## Open Items

- **AToM-OpenMM checkpoint glob pattern** — what files does AToM actually write? Confirm during end-to-end testing.
- **Salad GPU model strings** — the `VRAM_TIERS` dict in `scheduling.py` needs exact `nvidia-smi` model name strings from real Salad nodes.
- **clusterB cross-cluster sbatch** — submitting SLURM jobs to clusterB from a clusterA-hosted orchestrator requires SSH. Not yet implemented.
