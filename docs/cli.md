# RelayMD Operator CLI

## Install

```bash
curl -L https://github.com/<org>/relaymd/releases/latest/download/relaymd-linux-x86_64 -o ~/bin/relaymd && chmod +x ~/bin/relaymd
```

## Config

The CLI reads the same YAML config file as the orchestrator:
- default: `~/.config/relaymd/config.yaml`
- override path: `RELAYMD_CONFIG=/absolute/path/to/config.yaml`

Start from [deploy/config.example.yaml](../deploy/config.example.yaml) and set:
- `orchestrator_url`
- `api_token`
- `b2_endpoint_url`
- `b2_bucket_name`
- `b2_access_key_id`
- `b2_secret_access_key`

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
relaymd jobs status <job-id>
relaymd jobs cancel <job-id>
relaymd jobs cancel <job-id> --force
relaymd jobs requeue <job-id>
```

Workers:

```bash
relaymd workers list
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
