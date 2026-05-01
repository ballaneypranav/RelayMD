# RelayMD: Worker Internals

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
    │       │       → SIGTERM to subprocess
    │       │       → wait for checkpoint newer than pre-shutdown baseline mtime
    │       │       → upload only if newer checkpoint exists
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

## Worker Stack

### Packaging

`relaymd-worker` is a pip-installable package installed inside the Apptainer/Docker image at build time. It is not installed on the host. The worker entrypoint is `python -m relaymd.worker` (also registered as a console script `relaymd-worker` inside the container).

### Configuration

`pydantic-settings` (`BaseSettings`) with env vars injected at container launch. The bootstrap token is the only value that must be injected externally; runtime defaults can be overridden with env vars:

```python
class WorkerSettings(BaseSettings):
    worker_platform: Literal["hpc", "salad"] = "salad"
    heartbeat_interval_seconds: int = 60
    checkpoint_poll_interval_seconds: int = 300
    orchestrator_timeout_seconds: float = 30.0
    sigterm_checkpoint_wait_seconds: int = 60
```

`checkpoint_poll_interval_seconds` defaults to `300` seconds and can be overridden via `CHECKPOINT_POLL_INTERVAL_SECONDS` (worker env var) or `worker_checkpoint_poll_interval_seconds` (orchestrator config rendered into the SLURM worker environment).
Per-job bundle config can override this default using `checkpoint_poll_interval_seconds` in `relaymd-worker.json` or `.toml`. Bundle values must be integers `>= 1`.

On HPC, `SLURM_JOB_ID` is automatically present in the environment. The worker reads it and passes it as `slurm_job_id` in `POST /workers/register`. The orchestrator uses this to delete the matching placeholder row atomically, preventing duplicate worker entries in the UI.

### Secret Bootstrap

The bootstrap token is injected via SLURM's `--export` env var (never written to disk) or the Salad dashboard environment. From it, Infisical provides all other secrets: B2 credentials, the Tailscale ephemeral auth key, the orchestrator API token.

### Tailscale

`tailscale` binary invoked as a subprocess. The worker calls:

```
tailscale up --tun=userspace-networking --authkey=<key> --hostname=relaymd-worker-<worker_id>
```

No Python SDK — the binary is included in the container image. Userspace networking requires no root, which is essential for HPC. Both connection endpoints are tunneled via SOCKS5 inside the process namespace if possible to mitigate namespace leaks.

### GPU Detection

`pynvml` (NVIDIA Python bindings for NVML). Used at startup to detect GPU count, model name, and VRAM. Falls back gracefully if no GPU is present (for local testing).

### Heartbeat Thread

A `threading.Thread` (daemon=True). The main loop is synchronous (it blocks on a subprocess). The heartbeat runs in a separate OS thread. A `threading.Event` stops it cleanly when the main loop exits.

### Runtime Seams

Worker control flow is implemented as one procedural loop with explicit seams:
- `OrchestratorGateway` for API transport and conflict normalization
- `JobExecution` for non-blocking subprocess lifecycle and checkpoint polling

---

## Checkpoint Strategy

Filesystem polling defaults to every 5 minutes (`300s`) unless overridden by the bundle. The worker polls the simulation working directory for a file matching the `checkpoint_glob_pattern` from `relaymd-worker.json`. When a newer one is found, it uploads to B2 and reports immediately.

On wall-time margin (`slurm_sigterm_margin_seconds`, default 300s via `#SBATCH --signal=TERM@300`), the worker sends SIGTERM to the subprocess and snapshots a pre-shutdown checkpoint mtime baseline. It then waits up to `sigterm_checkpoint_wait_seconds` (default 60s) for a checkpoint that is strictly newer than that baseline. This prevents stale re-uploads during handoff races. If no newer checkpoint appears, the worker exits without uploading an older one.

The exact glob pattern for AToM-OpenMM checkpoints is to be confirmed during end-to-end testing.

---

## Input Bundle Format

The input bundle is a `.tar.gz` archive containing all simulation input files plus a mandatory config file:

```
relaymd-worker.json   (or .toml)
  └── command: "python run_atom.py --config simulation.json"
  └── checkpoint_glob_pattern: "*.chk"
  └── checkpoint_poll_interval_seconds: 60   # optional, per-job override
```

The archive root must be flat — no leading path component. The worker extracts it to a temp directory and runs the command from within that directory.
