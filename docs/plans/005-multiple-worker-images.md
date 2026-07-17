# Plan 005: Multiple RelayMD Worker Images

## Goal

Allow each RelayMD job to select one of a small, operator-controlled set of
worker images. Rename the current worker image to **AToM-OpenMM** and add a
RelayMD-compatible **GCNCMC-MD** image based on:

`/scratch/gilbreth/pballane/folate-alpha-beta/gcncmcmd/scripts/apptainer/gcncmcmd-production.def`

The selected image must be preserved with the job and enforced during worker
provisioning and assignment.

## Scope

- Add an allowlisted worker-image profile catalog to orchestrator
  configuration.
- Persist a stable image profile key on jobs and workers.
- Add `relaymd submit --worker-image <key>`.
- Make SLURM provisioning, placeholder activation, and worker assignment
  image-aware.
- Split the current worker build into a shared RelayMD app layer and
  workload-specific simulation base images.
- Publish OCI and Apptainer artifacts for AToM-OpenMM and GCNCMC-MD.
- Update local build, release, upgrade, configuration, CLI, API, frontend, and
  operator documentation paths.
- Keep arbitrary per-job image URIs out of scope.
- Treat multi-image SaladCloud provisioning as a later phase; existing Salad
  workers advertise the configured default image and can only claim matching
  jobs.

## Current-State Findings

1. `Dockerfile.worker-base` contains CUDA, Python 3.11, Tailscale, OpenMM 8.4,
   and pinned AToM-OpenMM. The root `Dockerfile` adds the RelayMD packages and
   starts `python -m relaymd.worker`.
2. `ClusterConfig` currently accepts exactly one `sif_path` or `image_uri`.
   `_render_sbatch_script` resolves that cluster-level source before any worker
   asks for a job.
3. Jobs and workers do not record an image identity. Assignment filters by
   cluster affinity only, so adding a second image without new identity fields
   could let a worker claim an incompatible job.
4. SLURM provisioning selects an affinity-compatible queued job but creates a
   generic placeholder. Active/pending checks are not image-aware.
5. The GCNCMC definition creates a Python 3.12 environment containing OpenMM
   8.2.0, openmmtools 0.24.2, CUDA 12.6, GRAND 1.1.0, and the other packages
   pinned by `openmm.yml`. It does not install Tailscale, RelayMD, or the
   RelayMD worker entrypoint.
6. The GCNCMC environment is materially different from the AToM environment:
   AToM currently uses Python 3.11 and OpenMM 8.4. Combining both environments
   in one base would create dependency conflicts and a much larger image.
7. The referenced GCNCMC definition copies `openmm.yml` and a local `grand`
   tree from its build context. RelayMD replaces that local checkout with the
   public HTTPS `essex-lab/grand` source pinned to the `v1.1.0` release commit
   `f58784faeaaabbe054b306f7a474e0eaec5ff878`.

## Locked Decisions

1. Jobs select a stable, lowercase profile key:
   - `atom-openmm`, displayed as `AToM-OpenMM`
   - `gcncmcmd`, displayed as `GCNCMC-MD`
2. The public CLI flag is `--worker-image`; API and persisted model fields use
   `worker_image_key` so the value is not confused with an OCI URI.
3. A job never accepts a raw image URI or SIF path. Operators configure the
   allowlisted key-to-source mapping.
4. `atom-openmm` is the initial default. Job creation resolves an omitted value
   to the configured default and persists it, so a later default change cannot
   silently change an existing queued or requeued job.
5. Existing jobs are migrated to `atom-openmm`.
6. Requeue clones preserve `worker_image_key`.
7. Workers advertise their image key at registration. Assignment requires an
   exact job/worker key match in addition to existing cluster affinity.
8. SLURM placeholders also store the image key. Registration activates only a
   placeholder with the same provider ID and image key.
9. The orchestrator chooses the image source; the worker does not inspect the
   job and relaunch itself into another container.
10. Image keys are workload compatibility contracts, not release versions.
    Configured sources must use immutable SHA tags, digests, or versioned SIF
    paths.
11. Use separate AToM-OpenMM and GCNCMC-MD simulation bases with one shared
    RelayMD app-layer recipe.
12. Keep a temporary `relaymd-worker` artifact/SIF alias pointing to
    AToM-OpenMM during migration, but use explicit names in new configuration.
13. First implementation supports per-job image provisioning on SLURM/HPC.
    Salad workers are explicitly tagged with one image key and cannot claim
    jobs for another image.

## Recommended Configuration Contract

Define the catalog once and let each cluster map supported keys to sources.
Keeping sources under the cluster preserves the existing ability to use
cluster-specific shared paths while still supporting registry URIs.

```yaml
default_worker_image: atom-openmm

worker_image_profiles:
  atom-openmm:
    display_name: AToM-OpenMM
  gcncmcmd:
    display_name: GCNCMC-MD

slurm_cluster_configs:
  - name: gilbreth-a30
    # Existing scheduler fields omitted.
    worker_images:
      atom-openmm:
        sif_path: /depot/plow/apps/relaymd/current/relaymd-worker-atom-openmm.sif
      gcncmcmd:
        sif_path: /depot/plow/apps/relaymd/current/relaymd-worker-gcncmcmd.sif
```

Each `worker_images.<key>` source uses the existing exactly-one-of
`sif_path`/`image_uri` validation and optional `sif_cache_dir`. Registry
sources continue to use the existing URI normalization and image-keyed
Apptainer cache.

Validation at startup must reject:

- an unknown `default_worker_image`;
- a cluster image key absent from `worker_image_profiles`;
- an image source with neither or both of `sif_path` and `image_uri`;
- a deployment in which the default image is not supported by any enabled
  compute backend.

For one compatibility release, legacy cluster-level `sif_path`/`image_uri`
may be translated to `worker_images.atom-openmm` with a deprecation warning.
New examples and generated configuration must use `worker_images`.

## API and Persistence Changes

Add `worker_image_key: str` to:

- `Job`, `JobCreate`, and `JobRead`;
- `Worker`, `WorkerRegister`, and `WorkerRead`;
- generated API client models;
- CLI JSON and job export output;
- frontend job and worker types.

Database migration:

1. Add nullable `job.worker_image_key` and `worker.worker_image_key`.
2. Backfill existing jobs and workers with `atom-openmm`.
3. Make both columns non-null with the application default
   `atom-openmm`.

Job creation behavior:

- Omitted key resolves to `default_worker_image`.
- Unknown key returns a typed validation error.
- A known key with no configured cluster remains queued only if another
  configured backend advertises it; otherwise reject submission with a clear
  unsupported-image error.
- Include the resolved key in the `created` history event and structured log.
- Keep the image key immutable for the lifetime of a job ID.

Add an operator-readable endpoint or extend the existing frontend config
endpoint to return available profiles:

```json
{
  "default_worker_image": "atom-openmm",
  "worker_images": [
    {"key": "atom-openmm", "display_name": "AToM-OpenMM"},
    {"key": "gcncmcmd", "display_name": "GCNCMC-MD"}
  ]
}
```

This lets CLI/UI discover valid choices without duplicating them in client
code.

## CLI and Frontend Behavior

CLI:

- Add repeat-safe validation for
  `relaymd submit ... --worker-image gcncmcmd`.
- If omitted, let the server resolve and return the default.
- Validate against the discovered profile catalog when available, while
  retaining server-side validation as the source of truth.
- Show the resolved key and display name in successful human and JSON output.
- Add the key to job list/detail/export fields.

Frontend:

- Show an image selector populated from the profile catalog if/when job
  submission is exposed in the UI.
- Show image display name on job and worker detail/table surfaces.
- Render the stable key as a fallback if a historical key is no longer present
  in current configuration.

## Image-Aware Provisioning and Assignment

### SLURM provisioning

Extend `QueuedJobCandidate` with `worker_image_key`.

For each cluster:

1. Walk queued jobs in creation order.
2. Require cluster-affinity compatibility.
3. Require `job.worker_image_key` to exist in
   `cluster.worker_images`.
4. Resolve the matching source and pass it to `submit_slurm_job`.
5. Render that source into `job.sbatch.j2`.
6. Set `RELAYMD_WORKER_IMAGE_KEY=<key>` in the container environment.
7. Create the queued placeholder with the same key.

Active/pending worker checks must be scoped to `(cluster, worker_image_key)`.
An idle AToM-OpenMM worker must not suppress provisioning for a queued
GCNCMC-MD job. Define the existing `max_pending_jobs` limit as per
cluster/image pair for this first implementation and document the changed
meaning.

Extend queue diagnostics with image-specific reasons:

- `unsupported_worker_image`
- `no_enabled_image_compatible_clusters`

Keep job lifecycle status as `queued`; use `queue_blocked_reason` for operator
visibility as with cluster affinity.

### Worker registration

- Worker startup reads required `RELAYMD_WORKER_IMAGE_KEY`.
- HPC registration sends that key with the provider ID.
- Placeholder activation requires provider ID and key to match. A mismatch is
  a registration error and must not silently rewrite the placeholder.
- For a transition period, absence of the variable may default to
  `atom-openmm` with a warning. Remove that fallback after all deployed images
  advertise their key.

### Assignment

Update both requesting-worker and scheduled assignment paths so
`_worker_can_run_job` requires:

```text
cluster affinity matches
AND worker.worker_image_key == job.worker_image_key
```

The match must occur before the atomic claim. Add image keys to assignment
success/skip logs. Image matching belongs in the orchestrator, not in the
payload bundle config.

### SaladCloud

Add a single configured `salad_worker_image_key`, defaulting to
`atom-openmm`, and inject it into the existing container group. The assignment
filter then prevents that group from claiming GCNCMC-MD jobs. Supporting more
than one Salad image later requires a key-to-container-group map and
per-profile scaling; do not overload the existing single-group scaler in this
change.

## Worker Image Layout

Use lowercase, hyphenated filenames and artifact names even though display
names retain their scientific capitalization.

Proposed source layout:

```text
Dockerfile.worker                         # shared RelayMD app layer
Dockerfile.worker-atom-openmm-base        # renamed current worker base
Dockerfile.worker-gcncmcmd-base           # new GCNCMC simulation base
images/gcncmcmd/openmm.yml                # pinned environment input
deploy/hpc/apptainer/
  relaymd-worker-app.localdev.def         # shared RelayMD app layer
  relaymd-worker-atom-openmm-base.localdev.def
  relaymd-worker-gcncmcmd-base.localdev.def
```

`Dockerfile.worker` is the current root worker `Dockerfile`, renamed to make
its role explicit. It continues to accept `BASE_IMAGE`, copies the workspace
packages, installs them with `--no-deps`, and uses:

```dockerfile
ENTRYPOINT ["python", "-m", "relaymd.worker"]
```

Published artifacts:

```text
ghcr.io/<org>/relaymd-worker-atom-openmm:<immutable-tag>
ghcr.io/<org>/relaymd-worker-gcncmcmd:<immutable-tag>
ghcr.io/<org>/relaymd-worker-atom-openmm-base:<immutable-tag>
ghcr.io/<org>/relaymd-worker-gcncmcmd-base:<immutable-tag>

relaymd-worker-atom-openmm.sif
relaymd-worker-gcncmcmd.sif
```

Keep `ghcr.io/<org>/relaymd-worker` and `relaymd-worker.sif` as temporary
AToM-OpenMM compatibility aliases.

## AToM-OpenMM Image

Rename the current base without changing its software contract:

- CUDA runtime base;
- Python 3.11;
- OpenMM 8.4 and CUDA 12.6 runtime packages;
- pinned AToM-OpenMM commit
  `71f2f4e6b90f3cfd8ff3ab0ec46e32922e9c2f56`;
- Tailscale and RelayMD runtime dependencies.

Add labels:

```text
relaymd.component=worker
relaymd.worker_image_key=atom-openmm
relaymd.worker_image_name=AToM-OpenMM
```

Preserve the existing OpenMM and `atom_openmm` smoke imports.

## GCNCMC-MD Image

Create a new simulation base patterned after the current RelayMD worker base,
using the software contract from `gcncmcmd-production.def`.

### Base construction

1. Start from Ubuntu 22.04 or the same NVIDIA CUDA runtime family used by the
   AToM base. The host driver remains injected by Apptainer `--nv`.
2. Install the same RelayMD host tools as the AToM base: `bash`, `coreutils`,
   `tar`, `procps`, certificates, `curl`, `git`, `bzip2`, Tailscale, and `uv`.
3. Pin micromamba to `2.3.3` rather than using `latest`.
4. Copy the pinned GCNCMC `openmm.yml` into the RelayMD build context.
5. Remove the exported host `prefix`, and remove the `grand==1.1.0` pip entry
   before environment creation, matching the source definition.
6. Create `/opt/gcncmcmd` from that file. Its Python 3.12 satisfies
   `relaymd-worker`'s current `>=3.11,<3.13` constraint.
7. Install the selected GRAND source into `/opt/gcncmcmd` with `--no-deps`.
8. Install the RelayMD worker runtime dependencies missing from the exported
   environment (`boto3`, `infisical-python`, `nvidia-ml-py`, `orjson`,
   `pydantic-settings`, `structlog`, `tenacity`, and any transitive packages
   required by the locked worker package) before applying the shared app layer.
9. Put `/opt/gcncmcmd/bin` first on `PATH`, set `PYTHONNOUSERSITE=1`, and keep
   `OPENMM_CPU_THREADS=${OPENMM_CPU_THREADS:-1}`.
10. Symlink the environment's Python only if needed by build tooling; verify
    that the final `python` used by the worker is `/opt/gcncmcmd/bin/python`.

Do not base GCNCMC-MD on the AToM base. Their Python and OpenMM pins differ,
and carrying AToM into the GCNCMC image provides no runtime value.

### Reproducible GRAND source

The implementation must resolve GRAND provenance before enabling CI. Preferred
order:

Install GRAND from the public HTTPS source at
`https://github.com/essex-lab/grand.git` pinned to its `v1.1.0` release commit
`f58784faeaaabbe054b306f7a474e0eaec5ff878`. Do not make CI depend on
`/scratch/gilbreth/pballane/folate-alpha-beta/gcncmcmd/grand` or an SSH-only
Git remote.

### Image tests

The base test must run with the final worker Python and verify:

```python
import grand
import openmm
import openmmtools

assert grand.__version__ == "1.1.0"
assert openmm.version.version.startswith("8.2")
```

The final app image must also verify:

- `python -m relaymd.worker --help` or an equivalent non-network import smoke
  test;
- imports for `relaymd`, `relaymd_api_client`, and worker dependencies;
- the OpenMM CUDA platform in a GPU-enabled smoke environment;
- OCI and Apptainer builds use the same Python and package versions.

## CI, Release, and Local Build Changes

1. Replace singular worker build jobs with a two-profile matrix.
2. Give each base and app image a separate cache scope and path filter.
3. Build the shared RelayMD app layer twice, once with each base image.
4. Build and push a SIF for each final worker image.
5. Change the release manifest from singular worker fields to a map:

   ```json
   {
     "worker_images": {
       "atom-openmm": {
         "image_uri": "docker://...",
         "sif_uri": "oras://..."
       },
       "gcncmcmd": {
         "image_uri": "docker://...",
         "sif_uri": "oras://..."
       }
     }
   }
   ```

6. Retain legacy `worker_image` and `worker_sif_uri` fields pointing to
   AToM-OpenMM for one compatibility release.
7. Update `relaymd upgrade` and `deploy/hpc/relaymd-service-pull` to pull both
   named SIFs atomically into the release directory.
8. Promote the release only after both required worker artifacts and the
   orchestrator/CLI are available for the same source commit.
9. Update local Docker/Podman and direct Apptainer scripts to accept
   `--worker-image atom-openmm|gcncmcmd|all`; default `all` for release-like
   builds and `atom-openmm` for the fastest compatibility path.
10. Preserve `relaymd-worker.sif -> relaymd-worker-atom-openmm.sif` during the
    migration.

## Delivery Assessment

This work is too large and operationally coupled for one implementation pass.
It crosses five failure domains:

1. database and generated API compatibility;
2. worker registration and job-assignment correctness;
3. SLURM provisioning and placeholder accounting;
4. two independently reproducible scientific software images;
5. CI, release manifests, upgrade, activation, and rollback.

Implement it as the phases below. Each phase ends at a green, reviewable commit
where the existing AToM-OpenMM path still works. The phases may remain in one
pull request if review capacity allows, but do not squash away the commit
boundaries until the change has passed production smoke validation. If the
review becomes unwieldy, split after Phase 3 and after Phase 5:

- PR 1: control-plane identity and image-aware scheduling;
- PR 2: image recipes and local validation;
- PR 3: CI/release integration and operator surfaces.

Later PRs must branch from or wait for the earlier contract PR; do not maintain
competing definitions of image keys.

## Phased Implementation and Commit Points

### Phase 0: Freeze names and reproducible inputs

Work:

- Confirm the stable keys `atom-openmm` and `gcncmcmd`, display names, artifact
  names, environment paths, and compatibility aliases.
- Pin the GRAND source to `https://github.com/essex-lab/grand.git` at its
  `v1.1.0` release commit `f58784faeaaabbe054b306f7a474e0eaec5ff878`.
- Copy the pinned `openmm.yml` into an intentional RelayMD image-build input
  location.
- Add the ADR for allowlisted image profiles and record the source-provenance
  decision.

Commit point:

```text
docs(images): lock worker image profiles and GCNCMC build inputs
```

Exit criteria:

- A clean checkout can access every future image input without `/scratch`
  paths or SSH-only Git access.
- No runtime behavior changes.
- Image keys and artifact names are treated as frozen contracts for later
  phases.

### Phase 1: Add the backward-compatible configuration catalog

Work:

- Add `WorkerImageProfile` and image-source config models.
- Add `default_worker_image` and per-cluster `worker_images`.
- Translate legacy cluster-level `sif_path`/`image_uri` into
  `worker_images.atom-openmm` with a warning.
- Add startup validation and profile discovery serialization.
- Update focused configuration tests and the example config.

Commit point:

```text
feat(config): add worker image profile catalog
```

Exit criteria:

- Existing production configuration loads unchanged and resolves to
  `atom-openmm`.
- New two-image configuration validates.
- No database or scheduler behavior changes yet.

### Phase 2: Persist image identity through the API and workers

Work:

- Add `worker_image_key` to job and worker core models.
- Add and test the Alembic migration, including AToM backfill and non-null
  enforcement.
- Extend create/read/requeue/history and worker registration contracts.
- Make worker startup advertise `RELAYMD_WORKER_IMAGE_KEY`, with the temporary
  missing-value fallback to `atom-openmm`.
- Make placeholder activation reject provider/image mismatches.
- Regenerate the API client once the shared contract is complete.

Commit point:

```text
feat(api): persist worker image identity
```

Exit criteria:

- Existing jobs and workers read as `atom-openmm`.
- New records always persist an explicit key.
- Requeue clones and placeholder activation preserve the key.
- API, migration, worker gateway, and generated-client tests pass.
- Scheduling still behaves like the single-image system because all current
  jobs resolve to `atom-openmm`.

### Phase 3: Enforce image-aware assignment and SLURM provisioning

Work:

- Add exact image-key matching to requesting and scheduled assignment paths.
- Carry the key through `QueuedJobCandidate`, worker selection, sbatch
  rendering, environment injection, and placeholder creation.
- Scope active and pending worker checks to cluster/image pairs.
- Add image-specific queue-blocked reasons and structured logs.
- Define and test mixed-image FIFO behavior and per-image pending limits.
- Tag the existing Salad group as `atom-openmm` without adding multi-group
  scaling.

Commit point:

```text
feat(scheduler): provision and assign image-compatible workers
```

Exit criteria:

- Cross-image claims are impossible in tests.
- An AToM-only configuration remains behaviorally compatible.
- A synthetic two-image configuration renders the correct source for each
  queued job.
- Scheduler, assignment, registration, reaper, and sbatch tests pass.

This is the first safe split point for a standalone control-plane PR.

### Phase 4: Refactor AToM and build the GCNCMC worker locally

Work:

- Rename the generic RelayMD app layer and AToM base recipes.
- Add explicit image labels and `RELAYMD_WORKER_IMAGE_KEY` defaults.
- Add the GCNCMC Docker and Apptainer base recipes from the pinned inputs.
- Apply the shared RelayMD app layer to both bases.
- Update local build/conversion scripts for one profile or all profiles.
- Add import, version, entrypoint, and available GPU smoke checks.

Commit point:

```text
feat(images): add AToM-OpenMM and GCNCMC worker variants
```

Exit criteria:

- Both OCI images build from a clean checkout.
- Both local Apptainer artifacts build or have a clearly documented
  environment limitation.
- AToM uses Python 3.11/OpenMM 8.4 and GCNCMC uses Python 3.12/OpenMM 8.2.
- Both variants start the RelayMD worker with the intended environment Python.
- No CI or production release layout changes yet.

This is the second safe split point for an image-focused PR.

### Phase 5: Publish and activate a coherent two-image release

Work:

- Convert worker base, app, and SIF CI jobs to a profile matrix.
- Add per-profile path filters, caches, tags, and smoke tests.
- Extend the release manifest with `worker_images` while retaining AToM legacy
  aliases for one release.
- Update `relaymd upgrade`, `relaymd-service-pull`, release staging, atomic
  activation, rollback, and compatibility symlinks.
- Test partial-release failure: activation must not occur if either required
  worker artifact is absent.

Commit point:

```text
feat(release): publish and install multiple worker images
```

Exit criteria:

- CI pins both worker variants to the same source commit.
- A release installs both named SIFs before switching `current`.
- Rollback restores a complete prior image set.
- Shell syntax tests, release-script tests, and manifest tests pass.

### Phase 6: Expose selection to operators

Work:

- Add `relaymd submit --worker-image`.
- Add profile discovery, validation, and resolved selection to human and JSON
  output.
- Add image identity to CLI job/worker lists and exports.
- Add frontend types and image display fields; add a selector only if frontend
  submission is available.
- Regenerate the API client only if the contract changed since Phase 2.
- Update CLI and frontend tests.

Commit point:

```text
feat(cli): allow jobs to select a worker image
```

Exit criteria:

- Operators can explicitly submit `atom-openmm` and `gcncmcmd`.
- Invalid selections list available profiles.
- Historical keys missing from current config still render safely.
- CLI, frontend, and generated-client checks pass.

Operator selection deliberately comes after release tooling can publish and
install both images.

### Phase 7: Integration, documentation, and release version

Work:

- Update deployment, scheduling, lifecycle, worker, CLI, infra, HPC, SLURM,
  upgrade, and rollback documentation.
- Run both end-to-end smoke jobs and verify job, placeholder, worker, and
  assignment keys.
- Run targeted checks followed by full repository checks.
- Run `graphify update .`.
- Apply the repository-required CLI version bump with `make release-cli`.

Commit points:

```text
docs: document worker image selection and rollout
release: bump RelayMD CLI to X.Y.Z
```

Exit criteria:

- AToM and GCNCMC smoke jobs each run in their selected image.
- Full Python and frontend validation passes, or exact environmental blockers
  are recorded.
- The branch contains the version commit and matching tag required by
  repository policy.
- Branch and release tag are ready to push together.

## Parallel Implementation with Subagents

Use subagents only after Phase 0 freezes names and source inputs. The shared
model/config contract is the dependency for almost every other stream, so the
primary agent should own Phases 1 and 2 and should be the only agent editing
shared models, migrations, generated API client files, `pyproject.toml`, and
`uv.lock`.

With four total agent slots, use at most three subagents plus the primary
coordinator. Recommended ownership:

| Workstream | Earliest start | Exclusive ownership | Must not edit |
| --- | --- | --- | --- |
| Scheduler subagent | After Phase 2 | assignment service, SLURM provisioning/service tests, sbatch rendering tests | shared models, migrations, generated client, image recipes |
| Image subagent | After Phase 0 | Dockerfiles, `images/gcncmcmd`, Apptainer definitions, local image-build scripts, image smoke scripts | scheduler/API code, release manifest, version files |
| Interface subagent | After Phase 2 client generation | CLI submit/list/export, frontend types/views, their tests | shared API models, generated client, scheduler, CI |
| Release subagent | After Phase 4 artifact contract is stable | CI worker matrix, release manifest, upgrade/pull/install scripts and tests | image recipes, shared models, CLI version files |

The release subagent replaces the image or interface subagent in a later wave;
do not run four subagents alongside the primary agent.

### Recommended parallel waves

Wave 1:

- Primary agent: Phases 1 and 2, including the canonical contract and generated
  client.
- Image subagent: begin Phase 4 recipe work after Phase 0, using only the
  frozen keys and artifact names.

Wave 2, after Phase 2 is merged into the working branch:

- Scheduler subagent: Phase 3.
- Image subagent: finish Phase 4 and local smoke validation.
- Interface subagent: prepare Phase 6 against the generated client, but keep
  operator selection disabled from final integration until Phase 5 is ready.
- Primary agent: review cross-stream invariants, resolve contract questions,
  and run integration tests.

Wave 3:

- Release subagent: Phase 5 after final image names, paths, and build commands
  are stable.
- Interface subagent: finish Phase 6 tests and documentation notes.
- Primary agent: integrate in dependency order, run Phase 7, update graphify,
  and perform the version release commit.

### Coordination rules

- Give each subagent a bounded file set and require tests/evidence in its
  handoff. Avoid multiple agents editing `.github/workflows/ci.yml`,
  `deploy/hpc/relaymd-service-pull`, or generated client files.
- The primary agent integrates commits in phase order even if later work
  finishes earlier.
- Subagents must not independently regenerate the API client, update
  `graphify-out`, bump versions, create release tags, or rewrite `uv.lock`.
- Keep image-key literals centralized in shared configuration/model helpers;
  do not let subagents introduce separate CLI, frontend, scheduler, or shell
  enums.
- Before integrating each subagent result, rebase or replay it onto the latest
  completed phase and rerun the narrow tests for both sides of the boundary.
- After each wave, inspect `git diff`, confirm unrelated user changes remain
  untouched, and create the phase commit before starting the next integration
  wave.

## Validation Plan

Configuration:

- Reject duplicate/unknown profile keys and invalid image sources.
- Translate legacy single-image cluster config to `atom-openmm`.
- Reject a default key unsupported by all enabled backends.

API and persistence:

- Omitted image resolves to and persists `atom-openmm`.
- Explicit `gcncmcmd` survives create, read, list, history, and requeue clone.
- Unknown image selection returns a typed client-visible error.
- Migration backfills existing jobs/workers.

Provisioning:

- An AToM queued job renders the AToM source.
- A GCNCMC queued job renders the GCNCMC source.
- A cluster lacking the selected key is skipped and reports an image-specific
  blocked reason.
- Active/pending AToM workers do not suppress GCNCMC provisioning.
- Placeholder rows retain the selected key.
- Registration with a mismatched provider ID/image key fails safely.

Assignment:

- AToM workers cannot claim GCNCMC jobs and vice versa.
- Cluster affinity and image compatibility are both enforced.
- Mixed-image queues preserve FIFO order among jobs each worker can run
  without head-of-line blocking incompatible jobs.
- Legacy/default Salad workers only claim `atom-openmm`.

CLI and frontend:

- `--worker-image gcncmcmd` is included in the create request and success
  output.
- Invalid keys show available values.
- Job and worker tables render configured display names and tolerate removed
  historical profiles.

Images:

- Both OCI images build from a clean checkout.
- Both SIFs build from the published bases.
- AToM smoke test imports AToM-OpenMM and OpenMM 8.4.
- GCNCMC smoke test imports local GRAND 1.1.0, OpenMM 8.2, and openmmtools.
- Both final images start/import the RelayMD worker with their intended
  environment Python.
- A GPU smoke run confirms OpenMM reports `CUDA` under Docker GPU runtime and
  Apptainer `--nv`.

Release:

- Manifest pins both images/SIFs to one source commit.
- Upgrade installs both named SIFs before switching `current`.
- Compatibility aliases resolve to AToM-OpenMM.
- Rollback restores the prior complete two-image release.

## Rollout

1. Deploy code that understands both the legacy singular image config and the
   new profile map.
2. Publish both images and SIFs for one RelayMD release.
3. Install the release with named SIFs and the AToM compatibility symlink.
4. Update orchestrator config to list both keys for the target cluster.
5. Submit one explicit AToM smoke job and one explicit GCNCMC smoke job.
6. Confirm each placeholder, registered worker, assignment, and job record has
   the expected key.
7. Keep `atom-openmm` as the default until GCNCMC production validation is
   complete.
8. Remove legacy config/manifest aliases only in a later breaking release.

## Documentation Changes

Update during implementation:

- `deploy/config.example.yaml`
- `docs/deployment.md`
- `docs/scheduling.md`
- `docs/job-lifecycle.md`
- `docs/worker-internals.md`
- `docs/cli.md`
- `docs/infra.md`
- `deploy/hpc/README.md`
- `deploy/slurm/README.md`
- release-manifest and upgrade documentation

Add an ADR recording why RelayMD uses an allowlisted image profile key instead
of accepting raw per-job image URIs.
