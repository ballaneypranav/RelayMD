# RelayMD HPC Service Wrappers

These scripts standardize phase-1 operator workflows for a GHCR -> Apptainer
pull and tmux-managed orchestrator service.

## Paths and Layout

Default install layout:

- Releases: `/depot/plow/apps/relaymd/releases/<version>/`
- Active symlink: `/depot/plow/apps/relaymd/current`
- Orchestrator SIF: `/depot/plow/apps/relaymd/current/relaymd-orchestrator.sif`
- Worker SIF: `/depot/plow/apps/relaymd/current/relaymd-worker.sif`

Default state/config layout:

- State root: `/depot/plow/data/pballane/relaymd-service`
- Shared status file: `/depot/plow/data/pballane/relaymd-service/state/relaymd-service.status`
- Config file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- DB: `/depot/plow/data/pballane/relaymd-service/db/relaymd.db`
- Orchestrator logs: `/depot/plow/data/pballane/relaymd-service/logs/orchestrator`
- Cluster logs: `/depot/plow/data/pballane/relaymd-service/logs/slurm/<cluster>`

## Commands

Pull and activate a release:

```bash
./deploy/hpc/relaymd-service-pull <release-version> \
  docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

`relaymd-service-pull` uses scratch-backed Apptainer temp/cache by default:

- `${SCRATCH:-${RCAC_SCRATCH:-/scratch/gilbreth/$USER}}/relaymd-service/apptainer/tmp`
- `${SCRATCH:-${RCAC_SCRATCH:-/scratch/gilbreth/$USER}}/relaymd-service/apptainer/cache`

Start orchestrator service inside the active SIF:

```bash
./deploy/hpc/relaymd-service-up
```

Force takeover on this host (only when lock is stale):

```bash
./deploy/hpc/relaymd-service-up --force
```

Start dashboard proxy inside the active SIF:

```bash
./deploy/hpc/relaymd-service-proxy
```

Force takeover on this host (only when lock is stale):

```bash
./deploy/hpc/relaymd-service-proxy --force
```

`relaymd-service-proxy` reads `RELAYMD_API_TOKEN`,
`RELAYMD_DASHBOARD_USERNAME`, and `RELAYMD_DASHBOARD_PASSWORD` from the shell
or from `RELAYMD_ENV_FILE`.

## Frontend Pinning and Shared Lock

To avoid random-frontend startup drift, set a pinned frontend host in
`relaymd-service.env`:

```bash
RELAYMD_PRIMARY_HOST=gilbreth-fe03
```

`relaymd-service-up` and `relaymd-service-proxy` write a shared status file on
`/depot` with:

- host
- timestamp
- orchestrator/proxy active flags
- orchestrator/proxy ports

If the status file says RelayMD is active on another host, wrappers refuse to
start on the current host unless `--force` is passed.

## One-Time Setup

Install wrappers under the active release path and create a modulefile:

```bash
./deploy/hpc/install-service-layout.sh
```

Then load the module:

```bash
module use /depot/plow/apps/modulefiles
module load relaymd/current
```

After module load, wrappers are on `PATH` so you can run:

```bash
relaymd-service-pull ...
relaymd-service-up
relaymd-service-proxy
```

The installer seeds:

- `/depot/plow/apps/relaymd/bin/relaymd-service-*`
- `/depot/plow/apps/modulefiles/relaymd/current.lua`
- `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`

Edit `relaymd-service.env` and keep it private (`chmod 600`).
Use [relaymd-service.env.example](./relaymd-service.env.example) as the template.

## Overrides

You can override defaults through environment variables:

- `RELAYMD_SERVICE_ROOT`
- `RELAYMD_SCRATCH_ROOT`
- `CURRENT_LINK`
- `RELAYMD_DATA_ROOT`
- `RELAYMD_CONFIG`
- `RELAYMD_ENV_FILE`
- `RELAYMD_ORCHESTRATOR_SIF`
- `RELAYMD_BIND_PATHS`
- `RELAYMD_TAILSCALE_SOCKET`
- `RELAYMD_PRIMARY_HOST`
- `RELAYMD_STATUS_FILE`
- `ORCHESTRATOR_PORT`
- `PROXY_PORT`
- `APPTAINER_TMPDIR`
- `APPTAINER_CACHEDIR`

`relaymd-service-up` loads `RELAYMD_ENV_FILE`, injects runtime env vars into
the container via `APPTAINERENV_*`, and runs:

```bash
relaymd orchestrator up --host 127.0.0.1 --port 36158
```
