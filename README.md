# RelayMD

RelayMD is a distributed orchestration system for long-running molecular dynamics workloads across HPC and cloud GPU capacity; project design and implementation decisions are documented in [Architecture & Design](./architecture-and-design.md) and [Implementation Decisions & Stack Reference](./stack-and-implementation.md).

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
