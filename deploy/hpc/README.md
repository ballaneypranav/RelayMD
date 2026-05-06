# RelayMD HPC Service Deployment

The installed `relaymd` CLI standardizes a tmux-managed frontend deployment for RelayMD on HPC.
This deployment model remains intentionally login-node based (not Slurm service mode).

## Paths and Layout

Default install layout:

- Releases: `/depot/plow/apps/relaymd/releases/<version>/`
- Active symlink: `/depot/plow/apps/relaymd/current`
- Orchestrator SIF: `/depot/plow/apps/relaymd/current/relaymd-orchestrator.sif`
- Worker SIF: `/depot/plow/apps/relaymd/current/relaymd-worker.sif`
- CLI binary: `/depot/plow/apps/relaymd/current/relaymd`

Default state/config layout:

- State root: `/depot/plow/data/pballane/relaymd-service`
- Shared status file: `/depot/plow/data/pballane/relaymd-service/state/relaymd-service.status`
- Config file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml`
- Service env file: `/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env`
- Wrapper logs: `/depot/plow/data/pballane/relaymd-service/logs/service/`

## Commands

### Fast Local Dev Workflow (No GitHub Actions Wait)

Use this when iterating on branch code and you want local artifacts immediately.

1) Build local OCI images from current workspace:

```bash
make local-build-images
```

2) Build and activate local Apptainer runtime artifacts (supported default path):

```bash
make local-build-sif-or-sandbox
```

This uses local OCI image URIs (`docker-daemon://...`) and updates
`/depot/plow/apps/relaymd/current` to the chosen release directory.

3) Build and install local CLI into active service path:

```bash
make local-install-cli
```

4) Restart service and run fast smoke:

```bash
relaymd restart
make local-smoke
```

Alternative Apptainer `.def` path for HPC hosts with fakeroot:

```bash
make local-build-from-def
```

Fastest bind-mounted source path for branch iteration:

```bash
make local-activate-bind
RELAYMD_ENV_FILE=/depot/plow/data/pballane/relaymd-service/config/relaymd-local-bind.env relaymd restart
```

`local-activate-bind` runs `scripts/local_activate_bind_mount.sh`. It builds or
reuses only the local worker/orchestrator base SIFs, promotes those bases under
`current/`, writes a `current/relaymd` dev CLI wrapper, and writes an env overlay
that bind-mounts the current checkout into both the tmux-managed
orchestrator/proxy and Slurm worker jobs. Use this when Python source is changing
but runtime dependencies are not. Run `make frontend-build` first when frontend
assets changed, because the bind-mounted orchestrator serves `frontend/dist`.

`local-build-from-def` runs `scripts/local_build_from_def.sh`, which builds
worker and orchestrator artifacts directly from local source without Docker or
GitHub Actions. This path is for fast branch-local iteration only; production
rollouts still use GHCR images and `relaymd upgrade`.

The local `.def` flow uses reusable bases:

- `deploy/hpc/apptainer/relaymd-worker-base.localdev.def`
- `deploy/hpc/apptainer/relaymd-orchestrator-base.localdev.def`

The worker base contains the slow/stable runtime dependencies from
`Dockerfile.worker-base`: CUDA runtime, Python 3.11, Tailscale, micromamba,
OpenMM, pinned AToM-OpenMM, and the stable third-party Python dependencies used
by the RelayMD worker packages. The worker app def installs the current
workspace RelayMD source packages on top of that base without resolving
dependencies again.

The orchestrator base contains the slow/stable runtime dependencies from
`Dockerfile.orchestrator-base`: Python 3.11, Tailscale, `uv`, and Node 22. Node
is included in the local base because Apptainer builds are single-stage, while
the Docker orchestrator image uses a separate Node builder stage. The
orchestrator app def installs the current workspace RelayMD package and builds
frontend assets on top of that base.

Default base cache paths:

```text
build/local-def-stage/relaymd-worker-base.sif
build/local-def-stage/relaymd-orchestrator-base.sif
```

Fast default rebuild:

```bash
./scripts/local_build_from_def.sh --mode sandbox
```

Rebuild bases explicitly:

```bash
./scripts/local_build_from_def.sh --mode sandbox --rebuild-worker-base
./scripts/local_build_from_def.sh --mode sandbox --rebuild-orchestrator-base
./scripts/local_build_from_def.sh --mode sandbox --rebuild-bases
```

Use custom prebuilt bases:

```bash
./scripts/local_build_from_def.sh \
  --worker-base-sif /path/to/relaymd-worker-base.sif \
  --orchestrator-base-sif /path/to/relaymd-orchestrator-base.sif
```

`--mode sandbox` is the default and usually fastest for local development. It
builds directory sandboxes and creates compatibility symlinks named
`relaymd-worker.sif` and `relaymd-orchestrator.sif` in the activated release
directory. Use `--mode sif` when you need immutable single-file SIFs.

If you want `.def` failures to fall back to the local OCI conversion workflow,
run:

```bash
./scripts/local_build_from_def.sh --mode sandbox --fallback
```

Pull and activate using explicit image URIs (backward-compatible mode):

```bash
relaymd upgrade <release-version> \
  --orchestrator-image docker://ghcr.io/<org>/relaymd-orchestrator:sha-<shortsha> \
  --worker-image docker://ghcr.io/<org>/relaymd-worker:sha-<shortsha>
```

Each pull also installs a host-side `relaymd` CLI into the active release
directory and promotes it with the same `current` symlink.

Auto-resolve URIs from a tag (no copy/paste):

```bash
relaymd upgrade sha-<shortsha>
```

Auto-resolve latest pinned release set:

```bash
relaymd upgrade latest
```

`latest` first resolves from release manifest
`relaymd-release-manifest.json` (published to GitHub release tag `latest`),
which pins orchestrator image, worker image, and CLI URI together.
If manifest resolution fails, it falls back to newest shared `sha-*` present in
both `relaymd-orchestrator` and `relaymd-worker` package tags.

Dependencies for `latest` mode:

- `jq`
- one downloader (`curl` or `wget`) for manifest download
- `gh` and GitHub auth scope `read:packages` only for fallback path

Owner resolution for auto mode:

- `RELAYMD_GHCR_OWNER` if set
- else `gh repo view --json owner -q .owner.login`

`relaymd upgrade` defaults Apptainer temp/cache under `/tmp`:

- `/tmp/relaymd-service-$UID/apptainer/tmp`
- `/tmp/relaymd-service-$UID/apptainer/cache`

Start orchestrator and proxy:

```bash
relaymd up
```

Check live health:

```bash
relaymd status
relaymd status --verbose
```

Force takeover (only after confirming the other host is inactive):

```bash
relaymd up --force
```

Stop, restart, tail logs, or attach:

```bash
relaymd down
relaymd restart
relaymd logs --follow
relaymd attach --service orchestrator
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

`relaymd status` reports file metadata plus local tmux/port checks and
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
relaymd status

# local checks
TMUX='' tmux ls
ss -ltn | egrep ':(36158|36159)\b'

relaymd logs -n 80
```

Important: login-node services are non-durable and may be culled or restarted by
cluster operations. Use `relaymd status` and wrapper logs to detect
service drift quickly after reconnect/reboot windows.

## One-Time Setup

Install wrappers and modulefile:

```bash
./deploy/hpc/install-service-layout.sh
module use /depot/plow/apps/modulefiles
module load relaymd/current
```

After module load, the RelayMD CLI is on `PATH`:

```bash
relaymd --help
relaymd config show-paths
relaymd upgrade ...
relaymd up
relaymd status
```

Run smoke verification:

```bash
./deploy/hpc/relaymd-module-smoke-check
```

The installer seeds:

- `/depot/plow/apps/relaymd/bin/relaymd-service-*`
- `/depot/plow/apps/relaymd/bin/relaymd` (wrapper that dispatches to `current/relaymd`)
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
- `RELAYMD_RELEASE_MANIFEST_URI`
- `RELAYMD_CLI_URI`
- `RELAYMD_HEARTBEAT_INTERVAL_SECONDS`
- `RELAYMD_HEARTBEAT_STALE_SECONDS`
- `STARTUP_GRACE_SECONDS`
- `ORCHESTRATOR_PORT`
- `PROXY_PORT`
- `APPTAINER_TMPDIR`
- `APPTAINER_CACHEDIR`
