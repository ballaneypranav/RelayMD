# RelayMD

RelayMD is a distributed orchestration system for long-running molecular
dynamics workloads across HPC and cloud GPU capacity; project design and
implementation decisions are split across focused documents in `docs/`.

Start reading with:
- [Core Architecture](architecture.md)
- [Job Lifecycle](job-lifecycle.md)
- [Tech Stack & Development Guidelines](tech-stack.md)
- [Deployment Guide](deployment.md)

### Live Documentation

The full documentation is deployed to GitHub Pages at [https://ballaneypranav.github.io/RelayMD/](https://ballaneypranav.github.io/RelayMD/).

## Containers

RelayMD publishes both worker and orchestrator images to GHCR:

- `ghcr.io/<org>/relaymd-worker:<tag>`
- `ghcr.io/<org>/relaymd-orchestrator:<tag>`

Use immutable `sha-<shortsha>` tags for deploys.

Build and push commands:

```bash
make docker-build-worker ORG=<org>
make docker-push-worker ORG=<org>
make docker-build-orchestrator ORG=<org>
make docker-push-orchestrator ORG=<org>
```
