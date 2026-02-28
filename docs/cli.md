# RelayMD Operator CLI

## Install

```bash
curl -L https://github.com/<org>/relaymd/releases/latest/download/relaymd-linux-x86_64 -o ~/bin/relaymd && chmod +x ~/bin/relaymd
```

## Config 

The CLI reads the same YAML config chain as the orchestrator (highest precedence first):
- `RELAYMD_CONFIG=/absolute/path/to/config.yaml`
- `./relaymd-config.yaml` (project-local override, gitignored)
- `~/.config/relaymd/config.yaml` (user-global default)

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

Submit job:

```bash
relaymd submit ./my-input --title "my job"
```

Submit with command shortcut (writes `relaymd-worker.json` before packing):

```bash
relaymd submit ./my-input --title "my job" --command "python run.py" --checkpoint-glob "*.cpt"
```

Jobs:

```bash
relaymd jobs list
relaymd jobs list --pretty
relaymd jobs status <job-id>
relaymd jobs cancel <job-id>
relaymd jobs cancel <job-id> --force
relaymd jobs requeue <job-id>
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
```

## Orchestrator

Start orchestrator (defaults: `0.0.0.0:8000`):

```bash
relaymd orchestrator up
```

Override bind host and port:

```bash
relaymd orchestrator up --host 127.0.0.1 --port 9000
```

## relaymd-worker.json

`relaymd submit` requires a worker config in the input directory (`relaymd-worker.json` or `relaymd-worker.toml`) unless you pass `--command`.

Example JSON:

```json
{
  "command": "python run.py",
  "checkpoint_glob_pattern": "*.cpt"
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
