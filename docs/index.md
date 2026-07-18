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

RelayMD publishes two named worker profiles and an orchestrator image to GHCR:

- `ghcr.io/<org>/relaymd-worker-atom-openmm:<tag>`
- `ghcr.io/<org>/relaymd-worker-gcncmcmd:<tag>`
- `ghcr.io/<org>/relaymd-orchestrator:<tag>`

Use immutable `sha-<shortsha>` tags for deploys.

For branch-local HPC iteration, `make local-build-images` and
`make local-build-sif-or-sandbox` build the two named worker artifacts. See
[Deployment Guide](deployment.md) for the full local development workflow.

Build and push commands:

```bash
make docker-build-atom-openmm ORG=<org>
make docker-push-atom-openmm ORG=<org>
make docker-build-gcncmcmd ORG=<org>
make docker-push-gcncmcmd ORG=<org>
make docker-build-orchestrator ORG=<org>
make docker-push-orchestrator ORG=<org>
```
