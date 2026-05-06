# RelayMD Operator CLI

## Install

```bash
curl -L https://github.com/<org>/relaymd/releases/latest/download/relaymd-linux-x86_64 -o ~/bin/relaymd && chmod +x ~/bin/relaymd
```

## Config

On the HPC install, `module load relaymd/current` sets `RELAYMD_DATA_ROOT`; RelayMD then
derives the rest of the install paths from that directory:

- YAML config: `$RELAYMD_DATA_ROOT/config/relaymd-config.yaml`
- Private service env: `$RELAYMD_DATA_ROOT/config/relaymd-service.env`
- Status file: `$RELAYMD_DATA_ROOT/state/relaymd-service.status`
- Service logs: `$RELAYMD_DATA_ROOT/logs/service/`

Inspect the active paths with:

```bash
relaymd config show-paths
relaymd path data
relaymd path config
```

Config path selection is:

- `RELAYMD_CONFIG=/absolute/path/to/config.yaml`
- if `RELAYMD_DATA_ROOT` is set: `$RELAYMD_DATA_ROOT/config/relaymd-config.yaml`
- otherwise, standalone fallback paths: `~/.config/relaymd/config.yaml`, then
  `./relaymd-config.yaml`

Start from the reference config file (`deploy/config.example.yaml` in the repo) and set:
- `orchestrator_url` (Note: YAML configuration takes precedence over the `RELAYMD_ORCHESTRATOR_URL` environment variable)
- `api_token`
- `b2_endpoint_url`
- `b2_bucket_name`
- `b2_access_key_id`
- `b2_secret_access_key`
- `cf_worker_url` (if using Cloudflare proxy for downloads)
- `orchestrator_timeout_seconds` (optional)

`INFISICAL_TOKEN` must be set in the environment (for HPC service installs, set it
in `$RELAYMD_DATA_ROOT/config/relaymd-service.env`).

Environment overrides (take precedence over YAML):
- `RELAYMD_API_TOKEN` or `API_TOKEN`
- `INFISICAL_TOKEN` or `RELAYMD_INFISICAL_TOKEN`
- `B2_ENDPOINT_URL` or `B2_ENDPOINT`
- `B2_BUCKET_NAME` or `BUCKET_NAME`
- `B2_ACCESS_KEY_ID` or `B2_APPLICATION_KEY_ID`
- `B2_SECRET_ACCESS_KEY` or `B2_APPLICATION_KEY`
- `CF_WORKER_URL`
- `CF_BEARER_TOKEN` or `DOWNLOAD_BEARER_TOKEN`
- `RELAYMD_CLI_ORCHESTRATOR_TIMEOUT_SECONDS` (optional)

## Commands

Service lifecycle:

```bash
relaymd upgrade latest
relaymd up
relaymd status
relaymd status --verbose
relaymd logs --follow
relaymd attach --service orchestrator
relaymd restart
relaymd down
```

Submit job:

```bash
relaymd submit ./my-input --title "my job"
```

Submit with command shortcut (writes `relaymd-worker.json` before packing):

```bash
relaymd submit ./my-input --title "my job" --command "python run.py" --checkpoint-glob "*.cpt"
```

Submit machine-readable output:

```bash
relaymd submit ./my-input --title "my job" --json
```

On shared HPC installs, API-backed commands automatically delegate over SSH to
the host that owns the active RelayMD service lock when run from another login
node. This keeps the orchestrator bound to loopback on the service host while
allowing `submit`, `jobs`, `workers`, and `monitor` commands to be run from any
login shell with SSH access to the service host.

Jobs:

```bash
relaymd jobs list
relaymd jobs list --pretty
relaymd jobs show <job-id>
relaymd jobs cancel <job-id>
relaymd jobs cancel <job-id> --force
relaymd jobs requeue <job-id>
relaymd jobs checkpoint download <job-id>
```

When checkpoint download is delegated from a non-service login node, the
download command runs on the service host. Use an `--output` path on shared
storage if the file must be visible from the original shell.

Jobs JSON mode:

```bash
relaymd jobs list --json
relaymd jobs show <job-id> --json
relaymd jobs cancel <job-id> --json
relaymd jobs requeue <job-id> --json
relaymd jobs checkpoint download <job-id> --json
```

Strict transition rules apply:
- cancelling a running job without `--force` returns a conflict
- requeue is allowed only for terminal jobs (`completed`, `failed`, `cancelled`)

Monitor all jobs and workers concurrently (auto-refreshes every 3 seconds by default):

```bash
relaymd monitor
relaymd monitor --interval-seconds 5.0
```

Workers:

```bash
relaymd workers list
relaymd workers list --json
```

Paths and config JSON mode:

```bash
relaymd config show-paths --json
relaymd path config --json
```

Service status includes both process health and submit/service readiness:

```bash
relaymd status
relaymd status --json
```

On module-managed HPC installs, `relaymd status` performs live Infisical
hydration checks and reports redacted readiness blocks for config, secrets,
release assets, proxy auth, scheduler access, storage credentials, and network
socket state. From a non-service login node, status SSHes to the locked service
host so host-local checks such as tmux, ports, `sbatch`, SIF paths, and the
Tailscale socket are evaluated on the host that owns the service.

## Low-level Entrypoints

The service commands above are the public operator path. Container/runtime
entrypoints remain available for packaging and debugging:

- `relaymd-orchestrator`
- `relaymd-dashboard-proxy`
- `relaymd-worker`

## relaymd-worker.json

`relaymd submit` requires a worker config in the input directory (`relaymd-worker.json` or `relaymd-worker.toml`) unless you pass `--command`.
When `--command` is used, `--checkpoint-glob` is required.

Example JSON:

```json
{
  "command": "python run.py",
  "checkpoint_glob_pattern": "*.cpt",
  "checkpoint_poll_interval_seconds": 60,
  "progress_glob_pattern": ["progress", "run.log"],
  "startup_progress_timeout_seconds": 900,
  "progress_timeout_seconds": 1800,
  "max_runtime_seconds": 86400,
  "fatal_log_path": "run.log",
  "fatal_log_patterns": ["Traceback", "CUDA_ERROR", "Segmentation fault"]
}
```

The supervision fields are optional. When present, the worker treats missing
startup progress, stalled progress, max runtime expiry, or a fatal log match as
payload failure, terminates the whole process group, uploads any final checkpoint
it can find, and reports the job failed.

## Release Versioning

Work on a branch and merge through a pull request. Direct pushes to `main` are
blocked by repository policy, and release-producing changes should land through
CI with an explicit version bump.

Every pushed branch that changes source, tests, deployment assets, release
automation, or operator documentation should include an explicit version bump.
CLI-affecting branches must include a root `pyproject.toml` version bump before
merge. Keep `pyproject.toml`, `src/relaymd/_version.py`, and `uv.lock` in sync.

Use the helper script to bump version, update the lockfile, commit, and tag in
one step:

```bash
make release-cli VERSION=0.1.1
```

Push the feature branch and matching tag after bumping:

```bash
git push -u origin <branch>
git push origin v0.1.1
```

`make release-cli VERSION=0.1.1 PUSH=1` can push the generated commit and tag
when you are already on the intended branch.

Pull requests that change CLI-affecting files must bump the root
`pyproject.toml` version. CI enforces this so deployed `relaymd --version`
can be used to confirm a session is running the expected binary.

GitHub Actions builds immutable SHA-tagged CLI, worker, and orchestrator
artifacts, refreshes the `latest` GitHub Release, and publishes
`relaymd-release-manifest.json`. The manifest pins release version, image URIs,
CLI binary URI, CLI version, and source commit together; do not hand-edit it or
reuse old tags for new artifacts.
