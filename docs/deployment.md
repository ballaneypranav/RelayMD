# Orchestrator Persistent Deployment

RelayMD phase-1 HPC deployment uses two OCI images published to GHCR and pulled
as Apptainer SIFs on the login node:

- `ghcr.io/<org>/relaymd-orchestrator:<tag>`
- `ghcr.io/<org>/relaymd-worker:<tag>`

The supported deployment path is:

```text
OCI image -> GHCR -> apptainer pull on HPC
```

Local `apptainer build --fakeroot` is not part of the supported rollout path.

## Config and State

Keep runtime config outside the image and keep all mutable state on shared
storage.

Recommended defaults:

- Config: `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- DB: `/depot/plow/data/pballane/relaymd-service/db/relaymd.db`
- Orchestrator logs: `/depot/plow/data/pballane/relaymd-service/logs/orchestrator`
- SLURM worker logs: `/depot/plow/data/pballane/relaymd-service/logs/slurm/<cluster>`

Config lookup order (highest precedence first):

- `RELAYMD_CONFIG=/absolute/path/to/config.yaml`
- `./relaymd-config.yaml` (project-local override, gitignored)
- `~/.config/relaymd/config.yaml` (user-global default)

## Release Layout

Store immutable pulled SIFs under a versioned release path and promote by
symlink:

- Releases: `/depot/plow/apps/relaymd/releases/<version>/`
- Active release symlink: `/depot/plow/apps/relaymd/current`

Expected active SIFs:

- `/depot/plow/apps/relaymd/current/relaymd-orchestrator.sif`
- `/depot/plow/apps/relaymd/current/relaymd-worker.sif`

## Operator Wrappers

Use the HPC wrappers in `deploy/hpc/`:

- `relaymd-service-pull`
- `relaymd-service-up`
- `relaymd-service-proxy`

Pull and activate a release:

```bash
./deploy/hpc/relaymd-service-pull <release-version> \
  docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

Start service in tmux from the active release:

```bash
./deploy/hpc/relaymd-service-up
```

Start the dashboard proxy in tmux:

```bash
export RELAYMD_API_TOKEN=<relaymd-api-token>
export RELAYMD_DASHBOARD_USERNAME=<username>
export RELAYMD_DASHBOARD_PASSWORD=<password>
./deploy/hpc/relaymd-service-proxy
```

`relaymd-service-up` runs `relaymd orchestrator up` inside the orchestrator SIF
and exports `RELAYMD_CONFIG` so runtime config remains external/private.

## Dashboard Access

Use loopback binding and forward only proxy port `36159` to your laptop.

1. start orchestrator with `relaymd-service-up`
2. start proxy with `relaymd-service-proxy`
3. forward `36159` in VS Code/SSH tunnel

The proxy injects `RELAYMD_API_TOKEN` upstream, so browsers never need direct
API token handling.

## Rollout Order

1. pull/promote orchestrator + worker release with immutable SHA tags
2. start/restart orchestrator service from the new `current` symlink
3. update CLI binaries as needed
