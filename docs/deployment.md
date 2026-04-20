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

After loading the module, `relaymd-service-*` wrappers and `relaymd` are on
`PATH` (via `/depot/plow/apps/relaymd/bin`).

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
./deploy/hpc/relaymd-service-pull <release-version> \
  docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

This also downloads and activates a host-side `relaymd` CLI binary under
`/depot/plow/apps/relaymd/current/relaymd`.

Auto-resolve by tag:

```bash
./deploy/hpc/relaymd-service-pull sha-<shortsha>
```

Auto-resolve newest shared `sha-*` across orchestrator+worker:

```bash
./deploy/hpc/relaymd-service-pull latest
```

`relaymd-service-pull` defaults Apptainer build temp/cache to
`/tmp/relaymd-service-$UID` (override with `RELAYMD_SCRATCH_ROOT`,
`APPTAINER_TMPDIR`, or `APPTAINER_CACHEDIR`).

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
3. promote release; this also updates the active `relaymd` CLI binary
