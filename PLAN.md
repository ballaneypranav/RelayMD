# RelayMD HPC Image Deployment Plan

## Summary
- Extend the existing GitHub Actions + GHCR flow from the worker image to a **second image** for the orchestrator, with the React frontend bundled into that image.
- Deploy on HPC by **pulling Apptainer SIFs from GHCR**, not by building SIFs locally with `apptainer --fakeroot`.
- Keep the initial runtime model simple:
  - one orchestrator image
  - one worker image
  - no job-type-specific worker image selection yet
  - one operator-managed service
- Keep runtime config external to the images and deploy it as a private file on HPC. Keep mutable state on shared storage with absolute paths.

## Key Changes
- **CI / image build**
  - Add a new GitHub Actions job that builds and pushes `ghcr.io/<owner>/relaymd-orchestrator`.
  - Keep the existing `relaymd-base` and `relaymd-worker` pipeline unchanged except for any shared refactors needed for reuse.
  - Build the frontend during the orchestrator image build and copy the built assets into the image.
  - Tag the orchestrator image the same way as the worker image: `latest` plus pinned `sha-<shortsha>` tags.

- **Container contents**
  - Worker image remains what it is today: CUDA/runtime base plus `relaymd-core`, `relaymd-api-client`, and `relaymd-worker`; entrypoint stays `python -m relaymd.worker`.
  - Orchestrator image should include:
    - the `relaymd` package with CLI/orchestrator code
    - built frontend assets
    - runtime tools the orchestrator actually uses in-container, including `ssh`, `tailscale`, and `tailscaled`
  - Do not try to serve the frontend from a repo-relative path inside the image. Make the orchestrator load frontend assets from an in-image path or packaged resources.

- **HPC deployment shape**
  - Pull images on the login node with `apptainer pull ... docker://ghcr.io/...`.
  - Store immutable SIF artifacts under a versioned shared install path, for example:
    - `/depot/plow/apps/relaymd/releases/<version>/relaymd-orchestrator.sif`
    - `/depot/plow/apps/relaymd/releases/<version>/relaymd-worker.sif`
  - Keep a stable `/depot/plow/apps/relaymd/current` symlink to the active release.
  - Run the orchestrator via tmux from the orchestrator SIF, with binds for:
    - private runtime config
    - DB/log/state directories
    - any required tailscale socket/state location if persisted outside the image
  - Keep runtime state under `/depot/plow/data/pballane/relaymd-service`, not inside the SIF and not in `/tmp`.

- **Config and state**
  - Keep config templates in git under `deploy/`.
  - Deploy a private runtime config copy outside the image, pointed to by `RELAYMD_CONFIG`.
  - Set absolute paths for:
    - `database_url`
    - orchestrator `log_directory`
    - each cluster `log_directory`
  - Standardize paths:
    - DB: `/depot/plow/data/pballane/relaymd-service/db/relaymd.db`
    - Orchestrator logs and saved `.sbatch` scripts: `/depot/plow/data/pballane/relaymd-service/logs/orchestrator`
    - SLURM worker stdout/stderr: `/depot/plow/data/pballane/relaymd-service/logs/slurm/<cluster>`

- **Worker image policy**
  - Keep **one worker image contract** for phase 1.
  - Do not add job-type-specific image selection yet.
  - Preserve current behavior where worker image selection is operationally tied to cluster config, but standardize on one shared worker image in the deployed config to avoid accidental heterogeneity during the first rollout.
  - Document clearly that per-job image selection is not supported today and is deferred.

## Interfaces / Operational Commands
- Add image publish outputs in CI summaries for both worker and orchestrator image tags/digests.
- Add or replace HPC launcher wrappers so operators use stable commands like:
  - `relaymd-service-pull`
  - `relaymd-service-up`
  - `relaymd-service-proxy`
- These wrappers should:
  - reference the active SIF under `/depot/plow/apps/relaymd/current/`
  - export `RELAYMD_CONFIG`
  - bind the shared state directories
  - run `relaymd orchestrator up` inside the orchestrator image
- Keep `relaymd orchestrator up` as the supported service command. Do not reintroduce `run`.

## Test Plan
- **CI tests**
  - Verify the orchestrator image build succeeds and produces a runnable image with bundled frontend assets.
  - Add a smoke test that the orchestrator serves `/` successfully when frontend assets are present in-image.
- **Local/container tests**
  - Add tests for frontend asset lookup from the packaged/in-image path.
  - Keep current worker image tests unchanged except for any shared build refactor coverage.
- **HPC acceptance**
  - Pull the orchestrator SIF from GHCR on the login node.
  - Launch it under tmux with external config/state binds.
  - Verify:
    - `/healthz` responds
    - `/` serves the bundled frontend
    - DB is created in the shared data directory
    - orchestrator log file is written in the shared log directory
    - rendered `.sbatch` copies land under `.../logs/orchestrator/slurm/`
  - Submit a known test job and verify worker stdout/stderr land under the configured cluster log directory, not in unexpected default cwd locations.
- **Fakeroot validation note**
  - Record that local `apptainer --fakeroot` was probed on this HPC and failed due missing usable fakeroot/subuid support, so local fakeroot builds are not part of the supported deployment path.

## Assumptions and Defaults
- “Elsewhere” means **GitHub Actions building OCI images and publishing them to GHCR**.
- The orchestrator will be containerized in a **separate image** from the worker, not merged into the worker image.
- Phase 1 is still **operator-only** for service management and runtime config ownership.
- The deployment path is **OCI image -> GHCR -> `apptainer pull` on HPC**, not `apptainer build --fakeroot` on the cluster.
- Multiple worker images by job type are explicitly deferred until after the shared orchestrator/image deployment is stable.
