# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project Summary

RelayMD is a distributed orchestration system for long-running molecular dynamics
workloads across HPC and cloud GPU capacity.

The repo is a Python 3.11 `uv` workspace with:

- Root `relaymd` package: CLI, dashboard proxy, and FastAPI orchestrator.
- `packages/relaymd-core`: shared Pydantic/SQLModel models and storage client.
- `packages/relaymd-worker`: worker bootstrap, heartbeat, and job execution loop.
- `packages/relaymd-api-client`: generated OpenAPI Python client.
- `frontend/`: React/Vite operator UI served by the orchestrator.
- `deploy/`: SLURM, HPC service, Salad, and tmux deployment assets.
- `docs/`: architecture, deployment, internals, and operational guidance.

Start with `README.md`, then use these docs for context:

- `docs/architecture.md`
- `docs/job-lifecycle.md`
- `docs/tech-stack.md`
- `docs/deployment.md`
- `docs/orchestrator-internals.md`
- `docs/worker-internals.md`
- `docs/cli-internals.md`

## Development Environment

- Use Python 3.11. The repo has `.python-version` set to `3.11`.
- Use `uv` for local Python workflows. Do not introduce conda workflows.
- Keep npm work inside `frontend/`, using the repo-local cache style already used
  by the Makefile: `npm --cache ./.npm ...`.
- Keep generated/cache outputs out of source changes unless intentionally updating
  generated artifacts.

## Common Commands

Python:

```bash
uv sync --dev
uv run pytest
uv run ruff format .
uv run ruff check .
uv run pyright
```

Targeted Python checks:

```bash
uv run pytest tests/orchestrator
uv run pytest tests/cli
uv run pytest packages/relaymd-worker/tests
uv run pytest packages/relaymd-core/tests
uv run ruff check <path>
uv run pyright <path>
```

Frontend:

```bash
cd frontend
npm --cache ./.npm install
npm --cache ./.npm run build
npm --cache ./.npm test
```

Convenience targets:

```bash
make frontend-build
make setup-hooks
```

## Code Quality Rules

- Prefer small, focused changes with matching tests.
- Keep package boundaries intact:
  - Shared API/domain/storage models belong in `packages/relaymd-core`.
  - Worker-only logic belongs in `packages/relaymd-worker`.
  - Orchestrator API, scheduler, DB, and service logic belong in `src/relaymd/orchestrator`.
  - CLI command and operator-facing client behavior belongs in `src/relaymd/cli`.
- Use Pydantic/SQLModel models for structured data instead of untyped dicts passed
  between components.
- For logging, use `structlog` style keyword arguments. Do not use f-string log
  messages for structured events.
- Preserve typed FastAPI request/response models and update shared models when API
  contracts change.
- Add or update tests near the affected layer.
- Avoid broad rewrites of deployment scripts unless the task specifically requires
  operational behavior changes.

## Generated API Client

`packages/relaymd-api-client/src/relaymd_api_client` is generated from the
orchestrator OpenAPI schema.

When API routes or models change and the client must be refreshed, use:

```bash
./scripts/generate_api_client.sh
```

This updates:

- `packages/relaymd-api-client/openapi.json`
- `packages/relaymd-api-client/src/relaymd_api_client`

Do not hand-edit generated client files unless the user explicitly asks for a
temporary patch.

## Testing Guidance

- Run the narrowest relevant tests while iterating.
- Before finishing substantial Python changes, run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

- For frontend changes, run:

```bash
cd frontend
npm --cache ./.npm run build
npm --cache ./.npm test
```

- If a full suite is too expensive or blocked by environment constraints, report
  exactly which checks were run and which were not.

## Configuration, Secrets, and Deployments

- Do not commit real secrets, tokens, cluster credentials, or host-specific private
  paths.
- Use `deploy/config.example.yaml` and documented environment variables as examples.
- Runtime secrets commonly involve Infisical and Axiom; tests provide dummy values
  via `pyproject.toml`.
- Treat `deploy/hpc`, `deploy/slurm`, Dockerfiles, and release scripts as
  operational assets. Keep changes backward-compatible unless the task is explicitly
  a migration.

## Frontend Guidance

- The frontend is React 19 + Vite + TypeScript under `frontend/`.
- Preserve the existing UI structure and styling language unless asked to redesign.
- Keep API contract assumptions aligned with `src/relaymd/orchestrator` and shared
  models.
- Add or update Vitest tests for behavior changes.

## Git and Workspace Hygiene

- Do not revert user changes.
- Inspect `git status --short` before making edits and before final reporting.
- Avoid committing generated caches, virtual environments, coverage output,
  `__pycache__`, `.pytest_cache`, or `frontend/.npm`.
- Do not run destructive git commands unless the user explicitly requests them.

