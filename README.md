# RelayMD

RelayMD is a distributed orchestration system for long-running molecular dynamics workloads across HPC and cloud GPU capacity; project design and implementation decisions are split across several focused documents in the `docs/` directory.

Start reading with:
- [Core Architecture](architecture.md)
- [Job Lifecycle](job-lifecycle.md)
- [Tech Stack & Development Guidelines](tech-stack.md)

### Local Documentation Served

To view the full documentation site locally with live reload:
```bash
uv run mkdocs serve
```
Then visit `http://127.0.0.1:8000`.

## Container

RelayMD worker containers are published to GitHub Container Registry (GHCR) as
`ghcr.io/<org>/relaymd-worker:latest`.

Build and push commands:

```bash
make docker-build ORG=<org>
make docker-push ORG=<org>
```

The worker entrypoint is `python -m relaymd.worker`. Provide
`INFISICAL_TOKEN=<client_id>:<client_secret>` when running the container so
bootstrap can retrieve runtime secrets.
