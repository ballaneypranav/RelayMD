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

- Data root: `/depot/plow/data/pballane/relaymd-service`
- Config: `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- Service env file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`
- DB: `/depot/plow/data/pballane/relaymd-service/db/relaymd.db`
- Orchestrator logs: `/depot/plow/data/pballane/relaymd-service/logs/orchestrator`
- SLURM worker logs: `/depot/plow/data/pballane/relaymd-service/logs/slurm/<cluster>`

Config path selection:

- `RELAYMD_CONFIG=/absolute/path/to/config.yaml`
- if `RELAYMD_DATA_ROOT` is set: `$RELAYMD_DATA_ROOT/config/relaymd-config.yaml`
- otherwise, standalone fallback paths: `~/.config/relaymd/config.yaml`, then
  `./relaymd-config.yaml`

The modulefile sets `RELAYMD_SERVICE_ROOT` and `RELAYMD_DATA_ROOT`; RelayMD derives
the config, env, status, and service-log paths from those roots. Inspect the
active install with `relaymd config show-paths`.

Worker checkpoint polling default:

- `worker_checkpoint_poll_interval_seconds: 300` (default)
- Rendered to worker runtime as `CHECKPOINT_POLL_INTERVAL_SECONDS`

Worker runtime contract for AToM jobs:

- Worker image includes `bash`, `python`, `tar`, `timeout` (coreutils), and standard shell tooling.
- Worker image installs pinned AToM-OpenMM Python package(s); keep the image clean (no `/depot/...` compatibility paths baked into the container).
- Set `ats_dir` in your submit-side config/bundle generation to the installed
  module path in the worker runtime, for example:
  `python -c "import pathlib, atom_openmm; print(pathlib.Path(atom_openmm.__file__).resolve().parent)"`

## Release Layout

Store immutable pulled SIFs under a versioned release path and promote by
symlink:

- Releases: `/depot/plow/apps/relaymd/releases/<version>/`
- Active release symlink: `/depot/plow/apps/relaymd/current`

Expected active SIFs:

- `/depot/plow/apps/relaymd/current/relaymd-orchestrator.sif`
- `/depot/plow/apps/relaymd/current/relaymd-worker.sif`
- `/depot/plow/apps/relaymd/current/relaymd`

## Operator CLI

Use the public `relaymd` CLI for service operations:

- `relaymd upgrade`
- `relaymd up`
- `relaymd status`
- `relaymd logs`
- `relaymd down`

Install wrappers/modulefile once:

```bash
./deploy/hpc/install-service-layout.sh
module use /depot/plow/apps/modulefiles
module load relaymd/current
```

After loading the module, `relaymd` is on `PATH` via
`/depot/plow/apps/relaymd/bin`.

Validate CLI exposure:

```bash
which relaymd
relaymd --help
relaymd submit --help
```

Automated smoke check:

```bash
./deploy/hpc/relaymd-module-smoke-check
```

Pull and activate a release:

```bash
relaymd upgrade <release-version> \
  --orchestrator-image docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  --worker-image docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

This also downloads and activates a host-side `relaymd` CLI binary under
`/depot/plow/apps/relaymd/current/relaymd`.

Auto-resolve by tag:

```bash
relaymd upgrade sha-<shortsha>
```

Auto-resolve latest pinned release set:

```bash
relaymd upgrade latest
```

`latest` resolves from release manifest
`relaymd-release-manifest.json` on GitHub release `latest`, so orchestrator,
worker, and CLI are promoted as one pinned set. If manifest resolution fails,
`relaymd upgrade` falls back to newest shared `sha-*` image tag discovery.

`relaymd upgrade` defaults Apptainer build temp/cache to
`/tmp/relaymd-service-$UID` (override with `RELAYMD_SCRATCH_ROOT`,
`APPTAINER_TMPDIR`, or `APPTAINER_CACHEDIR`).

Start service in tmux from the active release:

```bash
relaymd up
```

Check live status (heartbeat freshness + tmux + ports):

```bash
relaymd status
```

`relaymd up` starts the orchestrator and dashboard proxy through the installed
service wrappers. Runtime env vars from `relaymd-service.env`/shell env are
injected into the container using `APPTAINERENV_*` so config and secrets remain
external/private. Wrappers persist service logs under
`/depot/plow/data/pballane/relaymd-service/logs/service/` and record
start/exit metadata plus heartbeat updates in the shared status file.

## Dashboard Access

Use loopback binding and forward only proxy port `36159` to your laptop.

1. start services with `relaymd up`
2. forward `36159` in VS Code/SSH tunnel

The proxy injects `RELAYMD_API_TOKEN` upstream, so browsers never need direct
API token handling.

Note: login-node tmux services are non-durable and can be culled/restarted by
cluster maintenance. Operationally, use `relaymd status` and wrapper
logs to verify service health after reconnects or host events.

## Rollout Order

1. pull/promote orchestrator + worker release with immutable SHA tags
2. start/restart service from the new `current` symlink
3. promote release; this also updates the active `relaymd` CLI binary
