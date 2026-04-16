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

Start orchestrator service inside the active SIF:

```bash
./deploy/hpc/relaymd-service-up
```

Start dashboard proxy inside the active SIF:

```bash
export RELAYMD_API_TOKEN=<token>
export RELAYMD_DASHBOARD_USERNAME=<username>
export RELAYMD_DASHBOARD_PASSWORD=<password>
./deploy/hpc/relaymd-service-proxy
```

## Overrides

You can override defaults through environment variables:

- `RELAYMD_SERVICE_ROOT`
- `CURRENT_LINK`
- `RELAYMD_DATA_ROOT`
- `RELAYMD_CONFIG`
- `RELAYMD_ORCHESTRATOR_SIF`
- `RELAYMD_WORKER_SIF`
- `RELAYMD_BIND_PATHS`
- `RELAYMD_TAILSCALE_SOCKET`

`relaymd-service-up` exports `RELAYMD_CONFIG` and `RELAYMD_TAILSCALE_SOCKET`
inside the container and runs:

```bash
relaymd orchestrator up --host 127.0.0.1 --port 36158
```
