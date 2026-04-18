# RelayMD HPC Service Wrappers

These scripts standardize a tmux-managed frontend deployment for RelayMD on HPC.
This deployment model remains intentionally login-node based (not Slurm service mode).

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
- Service env file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`
- Wrapper logs: `/depot/plow/data/pballane/relaymd-service/logs/service/`

## Commands

Pull and activate using explicit image URIs (backward-compatible mode):

```bash
./deploy/hpc/relaymd-service-pull <release-version> \
  docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

Auto-resolve URIs from a tag (no copy/paste):

```bash
./deploy/hpc/relaymd-service-pull sha-<shortsha>
```

Auto-resolve newest shared `sha-*` tag across both packages:

```bash
./deploy/hpc/relaymd-service-pull latest
```

`latest` resolution policy is fixed: newest shared `sha-*` present in both
`relaymd-orchestrator` and `relaymd-worker` package tags.

Dependencies for `latest` mode:

- `gh` and `jq`
- GitHub auth scope `read:packages`

Owner resolution for auto mode:

- `RELAYMD_GHCR_OWNER` if set
- else `gh repo view --json owner -q .owner.login`

`relaymd-service-pull` uses scratch-backed Apptainer temp/cache by default:

- `${SCRATCH:-${RCAC_SCRATCH:-/scratch/gilbreth/$USER}}/relaymd-service/apptainer/tmp`
- `${SCRATCH:-${RCAC_SCRATCH:-/scratch/gilbreth/$USER}}/relaymd-service/apptainer/cache`

Start orchestrator:

```bash
./deploy/hpc/relaymd-service-up
```

Start proxy:

```bash
./deploy/hpc/relaymd-service-proxy
```

Check live health:

```bash
./deploy/hpc/relaymd-service-status
```

Force takeover (only after confirming the other host is inactive):

```bash
./deploy/hpc/relaymd-service-up --force
./deploy/hpc/relaymd-service-proxy --force
```

## Runtime Reliability Behavior

- `relaymd-service-up` and `relaymd-service-proxy` run pane commands via a
  supervised wrapper (`relaymd-service-supervise`).
- Wrapper logs are persistent:
  - `logs/service/orchestrator-wrapper.log`
  - `logs/service/proxy-wrapper.log`
- Each wrapper log includes start metadata (`host`, `command`, image path,
  session/port) and exit metadata (timestamp + exit code).
- Startup verification waits `STARTUP_GRACE_SECONDS` (default `3`). If the pane
  exits early, the wrapper prints an immediate failure summary and tails the log.
- Heartbeats are written while process is alive:
  - interval `RELAYMD_HEARTBEAT_INTERVAL_SECONDS` (default `30`)
  - stale threshold `RELAYMD_HEARTBEAT_STALE_SECONDS` (default `120`)

Status metadata fields include:

- `ORCHESTRATOR_HEARTBEAT_AT`, `PROXY_HEARTBEAT_AT`
- `ORCHESTRATOR_LAST_START_AT`, `ORCHESTRATOR_LAST_EXIT_AT`, `ORCHESTRATOR_LAST_EXIT_CODE`
- `PROXY_LAST_START_AT`, `PROXY_LAST_EXIT_AT`, `PROXY_LAST_EXIT_CODE`

`relaymd-service-status` reports file metadata plus local tmux/port checks and
returns exit code `0` only when orchestrator and proxy are both healthy on the
expected host.

## Frontend Pinning, Locking, and Stale Heartbeats

Set a pinned host in `relaymd-service.env`:

```bash
RELAYMD_PRIMARY_HOST=gilbreth-fe03
```

Cross-host lock enforcement remains enabled. Wrappers refuse startup if another
host is marked active unless `--force` is used.

Lock diagnostics now include heartbeat timestamp/age and the stale threshold,
so operators can see when the remote lock looks stale before a manual takeover.

## Operational Checks

Use these checks during incident response:

```bash
relaymd-service-status

# local checks
TMUX='' tmux ls
ss -ltn | egrep ':(36158|36159)\b'

tail -n 80 /depot/plow/data/pballane/relaymd-service/logs/service/orchestrator-wrapper.log
tail -n 80 /depot/plow/data/pballane/relaymd-service/logs/service/proxy-wrapper.log
```

Important: login-node services are non-durable and may be culled or restarted by
cluster operations. Use `relaymd-service-status` and wrapper logs to detect
service drift quickly after reconnect/reboot windows.

## One-Time Setup

Install wrappers and modulefile:

```bash
./deploy/hpc/install-service-layout.sh
module use /depot/plow/apps/modulefiles
module load relaymd/current
```

After module load, wrappers are on `PATH`:

```bash
relaymd-service-pull ...
relaymd-service-up
relaymd-service-proxy
relaymd-service-status
```

The installer seeds:

- `/depot/plow/apps/relaymd/bin/relaymd-service-*`
- `/depot/plow/apps/modulefiles/relaymd/current.lua`
- `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`

Edit `relaymd-service.env` and keep it private (`chmod 600`).
Use [relaymd-service.env.example](./relaymd-service.env.example) as template.

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
- `RELAYMD_GHCR_OWNER`
- `RELAYMD_HEARTBEAT_INTERVAL_SECONDS`
- `RELAYMD_HEARTBEAT_STALE_SECONDS`
- `STARTUP_GRACE_SECONDS`
- `ORCHESTRATOR_PORT`
- `PROXY_PORT`
- `APPTAINER_TMPDIR`
- `APPTAINER_CACHEDIR`
