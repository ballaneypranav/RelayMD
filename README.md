# RelayMD

RelayMD is a distributed orchestration system for long-running molecular dynamics workloads across HPC and cloud GPU capacity; project design and implementation decisions are split across several focused documents in the `docs/` directory.

Start reading with:
- [Core Architecture](docs/architecture.md)
- [Job Lifecycle](docs/job-lifecycle.md)
- [Tech Stack & Development Guidelines](docs/tech-stack.md)
- [Deployment Guide](docs/deployment.md)

### Live Documentation

The full documentation is deployed to GitHub Pages at [https://ballaneypranav.github.io/RelayMD/](https://ballaneypranav.github.io/RelayMD/).

## Containers

RelayMD publishes two images to GitHub Container Registry (GHCR):

- `ghcr.io/<org>/relaymd-worker:<tag>`
- `ghcr.io/<org>/relaymd-orchestrator:<tag>`

Build and push commands:

```bash
make docker-build-worker ORG=<org>
make docker-push-worker ORG=<org>
make docker-build-orchestrator ORG=<org>
make docker-push-orchestrator ORG=<org>
```

Worker entrypoint: `python -m relaymd.worker`.
Orchestrator entrypoint: `relaymd orchestrator up`.
Runtime requirement: set `INFISICAL_TOKEN=<client_id>:<client_secret>` for both
worker bootstrap and orchestrator startup.

## Development

### Frontend

The operator UI is built in `frontend/` and served by the orchestrator on port `36158`.

```bash
cd frontend
npm --cache ./.npm install
npm --cache ./.npm run build
```

### Git Hooks

This repository uses [Ruff](https://docs.astral.sh/ruff/) and [Pyright](https://microsoft.github.io/pyright/) for code quality. We use git hooks to ensure these checks are run before every commit.

To set up the hooks locally, run:

```bash
make setup-hooks
```

The hooks are stored in `.githooks/` and include:
- `pre-commit`: Runs `ruff format`, `ruff check --fix`, and `pyright`.
- `pre-push`: (Empty placeholder) Useful for longer-running checks like `pytest`.
