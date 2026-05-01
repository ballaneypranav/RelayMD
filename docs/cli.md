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
- `infisical_token` (optional; if set, CLI automatically hydrates missing API and B2 credentials from Infisical)
- `cf_worker_url` (if using Cloudflare proxy for downloads)
- `orchestrator_timeout_seconds` (optional)

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
  "checkpoint_poll_interval_seconds": 60
}
```

## Release Versioning

Use the helper script to bump version, update lockfile, commit, and tag in one step:

```bash
make release-cli VERSION=0.1.1
```

Push immediately after tagging:

```bash
make release-cli VERSION=0.1.1 PUSH=1
```
