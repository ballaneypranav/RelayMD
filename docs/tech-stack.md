# RelayMD: Tech Stack & Development Guidelines

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
│   ├── architecture.md
│   ├── scheduling.md
│   ├── api-schema.md
│   ├── cli.md                 # CLI install and usage guide
│   ├── deployment.md          # Orchestrator deployment guide
│   ├── hpc-notes.md           # Apptainer + Tailscale runbook
│   └── storage-layout.md
├── frontend/                  # React operator dashboard served by FastAPI
├── Dockerfile                 # Worker container image
└── pyproject.toml             # Root relaymd package + workspace config
```

`relaymd-core` is the shared dependency layer: it carries only `relaymd.models` + `relaymd.storage`. The worker container installs `relaymd-core` + `relaymd-worker` only; it does not install `relaymd` (and therefore does not pull FastAPI, uvicorn, alembic, or typer). A `uv` workspace at the repo root manages these three packages with one lockfile. The frontend uses npm under `frontend/`, with cache and build output kept inside the repo.

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

## Open Items

- **AToM-OpenMM checkpoint glob pattern** — what files does AToM actually write? Confirm during end-to-end testing.
- **Salad GPU model strings** — the `VRAM_TIERS` dict in `scheduling.py` needs exact `nvidia-smi` model name strings from real Salad nodes.
- **clusterB cross-cluster sbatch** — submitting SLURM jobs to clusterB from a clusterA-hosted orchestrator requires SSH. Not yet implemented.
