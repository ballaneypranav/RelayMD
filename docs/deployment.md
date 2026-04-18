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
- Service env file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`
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
- `relaymd-service-status`

Install wrappers/modulefile once:

```bash
./deploy/hpc/install-service-layout.sh
module use /depot/plow/apps/modulefiles
module load relaymd/current
```

After loading the module, `relaymd-service-*` wrappers are on `PATH`.

Pull and activate a release:

```bash
./deploy/hpc/relaymd-service-pull <release-version> \
  docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

Auto-resolve by tag:

```bash
./deploy/hpc/relaymd-service-pull sha-<shortsha>
```

Auto-resolve newest shared `sha-*` across orchestrator+worker:

```bash
./deploy/hpc/relaymd-service-pull latest
```

`relaymd-service-pull` defaults Apptainer build temp/cache to scratch-backed
directories to avoid `/tmp` space failures on login nodes.

Start service in tmux from the active release:

```bash
./deploy/hpc/relaymd-service-up
```

Start the dashboard proxy in tmux:

```bash
./deploy/hpc/relaymd-service-proxy
```

Check live status (heartbeat freshness + tmux + ports):

```bash
./deploy/hpc/relaymd-service-status
```

`relaymd-service-up` runs `relaymd orchestrator up` inside the orchestrator SIF
and injects runtime env vars from `relaymd-service.env`/shell env into the
container using `APPTAINERENV_*` so config and secrets remain external/private.
Wrappers now persist service logs under
`/depot/plow/data/pballane/relaymd-service/logs/service/` and record
start/exit metadata plus heartbeat updates in the shared status file.

## Dashboard Access

Use loopback binding and forward only proxy port `36159` to your laptop.

1. start orchestrator with `relaymd-service-up`
2. start proxy with `relaymd-service-proxy`
3. forward `36159` in VS Code/SSH tunnel

The proxy injects `RELAYMD_API_TOKEN` upstream, so browsers never need direct
API token handling.

Note: login-node tmux services are non-durable and can be culled/restarted by
cluster maintenance. Operationally, use `relaymd-service-status` and wrapper
logs to verify service health after reconnects or host events.

## Rollout Order

1. pull/promote orchestrator + worker release with immutable SHA tags
2. start/restart orchestrator service from the new `current` symlink
3. update CLI binaries as needed
