# Orchestrator Persistent Deployment

RelayMD publishes both Docker/OCI images and Apptainer SIFs. SaladCloud uses the
Docker images directly; HPC uses the matching SIF release artifacts when
available and falls back to `apptainer pull` from GHCR when needed:

- `ghcr.io/<org>/relaymd-orchestrator:<tag>`
- `ghcr.io/<org>/relaymd-worker-atom-openmm:<tag>`
- `ghcr.io/<org>/relaymd-worker-gcncmcmd:<tag>`

The supported production paths are:

```text
Docker image -> GHCR -> SaladCloud
Docker image -> GHCR -> prebuilt SIF release artifact -> HPC
```

Local `apptainer build --fakeroot` is for development iteration, not production
promotion.

For branch-local iteration without waiting for GitHub Actions, use the local
OCI conversion workflow. It produces the same named profile artifacts used in
production.

### Local OCI Conversion Workflow

Use this when Docker or Podman is available on the development host:

```bash
make local-build-images WORKER_PROFILE=all
make local-build-sif-or-sandbox WORKER_PROFILE=all
make local-install-cli
relaymd restart
make local-smoke
```

This builds local OCI images from the workspace, converts them to the
orchestrator, AToM-OpenMM, and GCNCMC-MD Apptainer artifacts, activates the
release directory, installs the local CLI binary, and restarts the service.
Worker and orchestrator conversions run in parallel. Use the profile-specific
script options only when intentionally iterating on one workload; a usable
two-profile release always contains both named worker artifacts.

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

## Worker Image Profiles

Jobs select a stable `worker_image_key`; deployments configure the allowed
sources rather than accepting a job-provided URI. The only supported keys are
`atom-openmm` (AToM-OpenMM) and `gcncmcmd` (GCNCMC-MD). Every enabled cluster
declares the sources it supports under `worker_images`:

```yaml
default_worker_image: atom-openmm
worker_image_profiles:
  atom-openmm:
    display_name: AToM-OpenMM
  gcncmcmd:
    display_name: GCNCMC-MD
slurm_cluster_configs:
  - name: example
    # Scheduler fields omitted.
    worker_images:
      atom-openmm:
        sif_path: /depot/plow/apps/relaymd/current/relaymd-worker-atom-openmm.sif
      gcncmcmd:
        sif_path: /depot/plow/apps/relaymd/current/relaymd-worker-gcncmcmd.sif
```

Each `worker_images.<key>` entry uses exactly one `sif_path` or `image_uri`.
Cluster-level image source fields are unsupported. Reset a pre-profile database
before upgrading; RelayMD does not backfill existing jobs or workers with an
image key.

The selected worker receives `RELAYMD_WORKER_IMAGE_KEY` from the scheduler and
must register the same key. AToM submit-side bundle generation can set `ats_dir`
to the installed module path, for example:
`python -c "import pathlib, atom_openmm; print(pathlib.Path(atom_openmm.__file__).resolve().parent)"`.

## Release Layout

Store immutable pulled SIFs under a versioned release path and promote by
symlink:

- Releases: `/depot/plow/apps/relaymd/releases/<version>/`
- Active release symlink: `/depot/plow/apps/relaymd/current`

Expected active SIFs:

- `/depot/plow/apps/relaymd/current/relaymd-orchestrator.sif`
- `/depot/plow/apps/relaymd/current/relaymd-worker-atom-openmm.sif`
- `/depot/plow/apps/relaymd/current/relaymd-worker-gcncmcmd.sif`
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
  --atom-openmm-image docker://ghcr.io/<org>/relaymd-worker-atom-openmm:sha-<shortsha> \
  --gcncmcmd-image docker://ghcr.io/<org>/relaymd-worker-gcncmcmd:sha-<shortsha>
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
orchestrator image, per-profile worker images, optional reusable base SIF URIs, CLI URI, CLI
version, and source commit together. Do not hand-edit release manifests or reuse
an old tag for new artifacts.

Auto-resolve by tag:

```bash
relaymd upgrade sha-<shortsha>
```

Auto-resolve latest pinned release set:

```bash
relaymd upgrade latest
```

`latest` resolves from release manifest
`relaymd-release-manifest.json` on GitHub release `latest`, so the orchestrator,
both worker profiles, and CLI are promoted as one pinned set. If manifest resolution fails,
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

The proxy hydrates `RELAYMD_API_TOKEN` and dashboard login credentials from
Infisical, then injects the API token upstream so browsers never need direct API
token handling.

Note: login-node tmux services are non-durable and can be culled/restarted by
cluster maintenance. Operationally, use `relaymd status` and wrapper
logs to verify service health after reconnects or host events.

## Rollout Order

1. pull/promote the orchestrator and both worker-profile artifacts with immutable SHA tags
2. start/restart service from the new `current` symlink
3. promote release; this also updates the active `relaymd` CLI binary
