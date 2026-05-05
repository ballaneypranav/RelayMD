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

For branch-local iteration without waiting for GitHub Actions, there are two
local helper workflows.

### Local OCI Conversion Workflow

Use this when Docker or Podman is available on the development host:

```bash
make local-build-images
make local-build-sif-or-sandbox
make local-install-cli
relaymd restart
make local-smoke
```

This builds local OCI images from the workspace, converts them to Apptainer
artifacts, activates the release directory, installs the local CLI binary, and
restarts the service.

### Local Apptainer Definition Workflow

Use this on HPC systems where Docker is unavailable but Apptainer fakeroot works:

```bash
make local-build-from-def
make local-install-cli
relaymd restart
make local-smoke
```

`scripts/local_build_from_def.sh` builds local-only Apptainer artifacts directly
from definition files under `deploy/hpc/apptainer/`. It does not change the
GitHub Actions or release workflow.

The `.def` workflow is split into reusable base layers and fast app layers:

- `relaymd-worker-base.localdev.def`: mirrors `Dockerfile.worker-base`; includes
  CUDA runtime, Python 3.11, Tailscale, micromamba, OpenMM, and pinned
  AToM-OpenMM.
- `relaymd-worker.localdev.def`: installs current workspace worker packages on
  top of the worker base.
- `relaymd-orchestrator-base.localdev.def`: mirrors
  `Dockerfile.orchestrator-base`; includes Python 3.11, Tailscale, `uv`, and
  Node 22 for local frontend builds.
- `relaymd-orchestrator.localdev.def`: installs current workspace orchestrator
  packages and bundles frontend assets on top of the orchestrator base.

Default reusable base SIFs are cached under `build/local-def-stage/`:

- `build/local-def-stage/relaymd-worker-base.sif`
- `build/local-def-stage/relaymd-orchestrator-base.sif`

Normal iteration reuses those bases:

```bash
./scripts/local_build_from_def.sh --mode sandbox
```

Rebuild a base only when the corresponding Docker base dependency set changes:

```bash
./scripts/local_build_from_def.sh --mode sandbox --rebuild-worker-base
./scripts/local_build_from_def.sh --mode sandbox --rebuild-orchestrator-base
./scripts/local_build_from_def.sh --mode sandbox --rebuild-bases
```

Use custom base paths when sharing prebuilt local bases:

```bash
./scripts/local_build_from_def.sh \
  --worker-base-sif /path/to/relaymd-worker-base.sif \
  --orchestrator-base-sif /path/to/relaymd-orchestrator-base.sif
```

`--mode sandbox` is the default and is preferred for local development because
it writes directory sandboxes instead of compressed SIF files. This is faster to
build and easier to inspect. The script creates compatibility symlinks named
`relaymd-worker.sif` and `relaymd-orchestrator.sif` pointing at the sandbox
directories so existing service paths keep working. Use `--mode sif` when you
need immutable single-file artifacts.

Add `--fallback` if you want a failed `.def` build to fall back to the local
OCI->Apptainer conversion workflow:

```bash
./scripts/local_build_from_def.sh --mode sandbox --fallback
```

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
- Treated as a fallback default; bundle-level `checkpoint_poll_interval_seconds`
  takes precedence per job.

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

Machine output for automation:

```bash
relaymd submit ./input --title "job" --json
relaymd jobs list --json
relaymd workers list --json
relaymd status --json
relaymd jobs checkpoint download <job-id> --json
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

## Branch, Version, and Release Flow

All deployment and release changes should start on a new branch. Do not push
directly to `main`; merge through a pull request so GitHub Actions can build and
publish a coherent release set.

Every pushed branch that changes source, tests, deployment assets, release
automation, or operator docs should carry an explicit version bump. For CLI-
affecting changes, bump the root RelayMD version with:

```bash
make release-cli VERSION=X.Y.Z
```

That keeps `pyproject.toml`, `src/relaymd/_version.py`, and `uv.lock` aligned
and creates the matching `vX.Y.Z` tag. Push both the branch and tag:

```bash
git push -u origin <branch>
git push origin vX.Y.Z
```

On protected-branch CI, GitHub Actions publishes immutable `sha-<shortsha>`
release artifacts, refreshes the `latest` GitHub Release, and uploads
`relaymd-release-manifest.json`. The manifest is the source of truth tying the
orchestrator image, worker image, CLI URI, CLI version, and source commit
together. Do not hand-edit release manifests or reuse an old tag for new
artifacts.

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
