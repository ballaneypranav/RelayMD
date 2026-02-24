# RelayMD: Implementation Decisions & Stack Reference

# RelayMD: Implementation Decisions & Stack Reference

This document records all concrete framework and tooling decisions for the RelayMD implementation. It is the authoritative reference when starting any issue. If a decision here conflicts with an issue description, this document wins — update the issue.

---

## Guiding Principles

**Apptainer-first.** The worker runs inside an Apptainer `.sif` container. All Python dependencies — including the MD engine and the `relaymd` worker package — must be installed inside the image. Do not rely on the host environment for anything.

**No conda environments.** Conda adds significant image size and slow solve times. Use pip inside the container image. The base image should provide a suitable Python (3.11+) directly.

**uv for out-of-container installs.** The orchestrator runs on the login node outside any container. If you need to install Python packages there, use `uv` — not pip, not conda. The orchestrator's dependencies should be managed with a `uv` lockfile committed to the repo.

**Pydantic everywhere.** All structured data — API request/response bodies, config objects, DB models, inter-component messages — should be typed with Pydantic. If you are writing a `dict` with string keys to pass data between functions, use a Pydantic model instead.

---

## Language & Runtime

| Decision | Choice | Rationale |
| -- | -- | -- |
| Language | Python 3.11+ | Required by AToM-OpenMM ecosystem; modern union types, `tomllib`, faster |
| Package manager (orchestrator) | `uv` | Fast, reproducible, lockfile-based; replaces pip on the login node |
| Package manager (container) | pip inside Apptainer/Docker | No conda; uv can also be used inside the Dockerfile for faster builds |
| Python typing | strict Pydantic throughout | See guiding principle above |

---

## Networking Constraint: All Communication is Worker-Initiated

**Salad Cloud blocks all inbound traffic to containers.** This is a hard platform constraint.

The rule is simple: **the orchestrator never initiates a connection to a worker.** Every interaction is a worker making an outbound HTTP request to the orchestrator. The orchestrator is always the server; workers are always the clients.

The worker lifecycle is designed so this constraint never requires a workaround — the orchestrator controls worker behaviour entirely through job assignment responses, not push signals.

---

## Worker Lifecycle

The worker runs a simple request-run-report loop. It never needs to be told to stop via a signal — the orchestrator withholds jobs when there is nothing to do, and the worker exits naturally.

```
worker boots → fetches secrets → joins Tailnet → registers with orchestrator
    │
    ▼
POST /jobs/request
    ├── response: job assigned
    │       │
    │       ▼
    │   download input bundle + latest checkpoint from B2
    │       │
    │       ▼
    │   launch MD subprocess
    │       │
    │       ├── every 60s: POST /workers/{id}/heartbeat
    │       ├── every 5min (poll): if new checkpoint → upload to B2
    │       │                      → POST /jobs/{id}/checkpoint
    │       │
    │       ├── on SIGTERM (wall time / Salad shutdown):
    │       │       send SIGTERM to subprocess → wait → upload checkpoint
    │       │       → POST /jobs/{id}/checkpoint → exit
    │       │       (orchestrator re-queues the job automatically)
    │       │
    │       └── on clean subprocess exit:
    │               POST /jobs/{id}/complete
    │               → loop back to POST /jobs/request
    │
    └── response: no job available → worker exits cleanly
```

Key points:

* The worker loops back to request another job immediately after completing one. This means a long-running simulation spanning multiple SLURM allocations can be served by the same worker container if wall time permits.
* When the operator wants to stop a worker gracefully, they simply cancel or complete all pending jobs. The next time the worker asks for a job, the orchestrator responds with "no job available" and the worker exits. No drain signal needed.
* SIGTERM (from SLURM wall time or Salad shutdown) is the only external interruption. It is handled by checkpointing and exiting; the job re-queues automatically and any future worker picks it up.

---

## Orchestrator Stack

### Web Framework

**FastAPI**, async throughout.

The orchestrator is entirely I/O-bound (SQLite reads/writes, HTTP responses). There is no CPU-heavy work. Async is the natural fit for FastAPI and avoids thread-safety concerns with SQLAlchemy's session management.

* All route handlers: `async def`
* Database calls: use SQLAlchemy async session (`AsyncSession`)
* No `run_in_executor` wrappers needed

### Database

**SQLite** via **SQLModel** (which wraps SQLAlchemy 2.0 + Pydantic).

SQLModel is chosen specifically because it unifies the ORM model and the Pydantic schema into a single class definition. This eliminates the boilerplate of maintaining separate `JobDB` and `JobResponse` classes.

```python
class Job(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    status: JobStatus  # StrEnum: queued | assigned | running | completed | failed | cancelled
    input_bundle_path: str
    latest_checkpoint_path: str | None = None
    assigned_worker_id: uuid.UUID | None = None

class Worker(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    platform: str
    gpu_model: str
    gpu_count: int
    vram_gb: int
    last_heartbeat: datetime
```

Migrations: **Alembic**. Even though the schema is simple, Alembic is worth it from day one — the schema will evolve and manual `ALTER TABLE` on a live orchestrator is risky.

### Configuration

**pydantic-settings** (`BaseSettings`).

All orchestrator config is read from environment variables or a `.env` file. No argparse, no ad-hoc `os.getenv()` calls scattered through the code.

```python
class OrchestratorSettings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./relaymd.db"
    api_token: str
    b2_endpoint_url: str
    b2_bucket_name: str
    heartbeat_timeout_multiplier: float = 2.0
    slurm_cluster_configs: list[ClusterConfig] = []

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

### Scheduling Loop

**asyncio background task via FastAPI** `lifespan`.

Two loops run as background coroutines started at app startup:

1. **Stale worker reaper** — runs every 30 seconds; marks workers stale if `last_heartbeat > heartbeat_interval * timeout_multiplier`; re-queues their jobs.
2. **sbatch submission loop** — runs every 60 seconds; checks if queued jobs exist with no registered HPC workers; submits new SLURM jobs if so.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task1 = asyncio.create_task(stale_worker_reaper_loop())
    task2 = asyncio.create_task(sbatch_submission_loop())
    yield
    task1.cancel()
    task2.cancel()
```

No APScheduler. No separate process. No cron.

### sbatch Submission

**Direct subprocess call** — no SSH, no paramiko.

The orchestrator runs directly on the HPC login node. `sbatch` is available in `PATH`. Submission is:

```python
result = await asyncio.create_subprocess_exec(
    "sbatch", "--parsable", rendered_script_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

The returned SLURM job ID is stored in the DB to prevent duplicate submissions during the SLURM pending window.

---

## Worker Stack

### Packaging

The worker is a pip-installable package (`relaymd-worker`) installed inside the Apptainer/Docker image at build time. It is not installed on the host.

Entrypoint: `python -m relaymd.worker` (registered as a console script too for convenience).

### Configuration

**pydantic-settings** (`BaseSettings`), same pattern as the orchestrator. All config comes from environment variables injected at container launch.

```python
class WorkerSettings(BaseSettings):
    infisical_token: str  # bootstrap token — only external injection needed
    platform: Literal["hpc", "salad"] = "hpc"
    wall_time_limit_seconds: int = 14400  # 4 hours
    wall_time_margin_seconds: int = 300   # send SIGTERM 5 min before wall time
    heartbeat_interval_seconds: int = 60
    checkpoint_poll_interval_seconds: int = 300
```

### Secret Bootstrap

**Infisical Python SDK** (`infisical-python`). The bootstrap token is the only value injected externally. All other secrets are fetched from Infisical at startup before anything else runs.

### Tailscale

`tailscale` binary invoked as a subprocess. The worker calls `tailscale up --tun=userspace-networking --authkey=<key> --hostname=relaymd-worker-<worker_id>` during bootstrap. No Python SDK — the binary is included in the container image.

### Heartbeat Thread

A `threading.Thread` (daemon=True). The main worker loop is not async — it runs a subprocess and waits for it. The heartbeat runs in a separate OS thread, not a coroutine.

The heartbeat thread does exactly one thing per cycle: `POST /workers/{id}/heartbeat`. Nothing else. A `threading.Event` signals the thread to stop cleanly when the main loop exits.

### GPU Detection

`pynvml` (the official NVIDIA Python bindings for NVML). Used at worker startup to detect GPU count, model name, and VRAM. Falls back gracefully if no GPU is present (for local testing).

---

## Checkpoint Strategy

**Filesystem polling, every 5 minutes.**

The worker polls the simulation working directory every `checkpoint_poll_interval_seconds` (default 300) for a newer checkpoint file. If one is found, it uploads it to B2 and reports `POST /jobs/{id}/checkpoint` to the orchestrator immediately.

On wall-time margin (5 minutes before expiry), the worker sends SIGTERM to the subprocess, waits up to 60 seconds for a clean exit and a final checkpoint write, then uploads and exits. The job re-queues automatically.

Worst-case checkpoint loss on a crash is 5 minutes.

**What counts as a checkpoint file:** determined by a configurable glob pattern in the job's input bundle metadata (e.g. `*.chk`, `checkpoint.xml`). Default: `*.chk`. Finalize the exact pattern during [W-167](https://linear.app/ballaneypranav/issue/W-167/end-to-end-integration-test-full-job-lifecycle-across-two-worker) (end-to-end test).

---

## Storage Module

`boto3` with the S3-compatible Backblaze B2 API for writes. Reads are proxied through the Cloudflare Worker URL.

The `StorageClient` class is a thin wrapper exposing only the operations RelayMD needs:

* `upload_file(local_path, b2_key)`
* `download_file(b2_key, local_path)`
* `list_keys(prefix)`

Write endpoint: B2 S3-compatible endpoint. Read endpoint: Cloudflare Worker URL. The client selects the endpoint automatically by operation type.

---

## Shared Data Models

All API request/response models live in `relaymd.models` — a package shared by both the orchestrator and the worker client. Both packages declare it as a dependency.

Using a shared models package ensures that the worker and orchestrator always agree on field names and types. If a field changes, it changes in one place and both sides break loudly at import time rather than silently at runtime.

---

## Logging

`structlog` with JSON output.

All log statements emit structured JSON. No f-string log messages. Key fields on every log line: `worker_id` (on workers), `job_id` (when in context), `event`, `level`, `timestamp`.

```python
log = structlog.get_logger()
log.info("checkpoint_uploaded", job_id=str(job_id), b2_key=key, size_bytes=size)
```

Configure `structlog` to use `orjson` renderer in production and `ConsoleRenderer` in development (detected via `RELAYMD_ENV=development`).

---

## Testing

| Layer | Framework | Notes |
| -- | -- | -- |
| Orchestrator API | `pytest` + `httpx` (`AsyncClient`) | In-memory SQLite DB per test |
| Worker logic | `pytest` + `unittest.mock` | Mock Infisical, B2, subprocess calls |
| Storage module | `pytest` + `moto` | `moto` mocks the S3/B2 API locally |
| Scheduling loops | `pytest` + `freezegun` | Freeze time to test stale worker detection |

---

## Container Registry

**GHCR (GitHub Container Registry).**

Images tagged as `ghcr.io/<org>/relaymd-worker:<tag>`. Free for public repositories, no rate limits, integrates with GitHub Actions CI.

---

## Repository Layout

```
relaymd/
├── packages/
│   ├── relaymd-models/        # Shared Pydantic models (relaymd.models)
│   ├── relaymd-storage/       # Storage client (relaymd.storage)
│   ├── relaymd-worker/        # Worker client (relaymd.worker)
│   └── relaymd-orchestrator/  # FastAPI app (relaymd.orchestrator)
├── deploy/
│   ├── slurm/                 # SLURM .sbatch.j2 templates
│   └── salad/                 # Salad Cloud container group config
├── Dockerfile                 # Worker container image
├── pyproject.toml             # Root uv workspace config
└── ui/                        # Streamlit dashboard
```

`relaymd-models` and `relaymd-storage` are local path dependencies of both `relaymd-worker` and `relaymd-orchestrator`. A `uv` workspace at the repo root manages all four packages with a single lockfile.

---

## Open Items

The following need real-world validation before they can be finalized:

* **Tailscale userspace networking throughput on HPC** — expected to be adequate for control traffic but needs validation on actual cluster hardware ([W-151](https://linear.app/ballaneypranav/issue/W-151/apptainer-sif-conversion-and-tailscale-userspace-networking-validation)).
* **AToM-OpenMM checkpoint glob pattern** — depends on what files AToM actually writes; determine during [W-167](https://linear.app/ballaneypranav/issue/W-167/end-to-end-integration-test-full-job-lifecycle-across-two-worker) (end-to-end test).
* **Salad GPU model strings** — the VRAM tier lookup table in [W-158](https://linear.app/ballaneypranav/issue/W-158/gpu-aware-job-assignment-policy-prefer-hpc-multi-gpu-fallback-to-salad) needs to be populated with exact `nvidia-smi` model name strings from real Salad nodes.