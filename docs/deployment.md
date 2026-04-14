# Orchestrator Persistent Deployment

Use tmux for persistent orchestrator processes. A shell-owned process is not production-safe because it dies when the terminal disconnects.

## YAML Config Template

Create `~/.config/relaymd/config.yaml` from the canonical template:

```bash
mkdir -p ~/.config/relaymd
cp deploy/config.example.yaml ~/.config/relaymd/config.yaml
chmod 600 ~/.config/relaymd/config.yaml
```

SQLite recommendation: keep the database in a stable persistent directory (for example `/srv/relaymd/orchestrator/relaymd.db`), not `/tmp`.

Config lookup order (highest precedence first):
- `RELAYMD_CONFIG=/absolute/path/to/config.yaml`
- `./relaymd-config.yaml` (project-local override, gitignored)
- `~/.config/relaymd/config.yaml` (user-global default)

To force a specific path, set:

```bash
export RELAYMD_CONFIG=/absolute/path/to/config.yaml
```

Secrets can stay out of the YAML file by overriding them via environment variables:
- `RELAYMD_API_TOKEN`
- `INFISICAL_TOKEN`
- `APPTAINER_DOCKER_USERNAME` / `APPTAINER_DOCKER_PASSWORD` (optional; for private `docker://` pulls)

When `INFISICAL_TOKEN` is configured and any `slurm_cluster_configs` entry uses
`image_uri`, orchestrator also hydrates missing values for:
- `APPTAINER_DOCKER_USERNAME`
- `APPTAINER_DOCKER_PASSWORD`

## tmux

Launcher script is at `deploy/tmux/start-orchestrator.sh`.
It launches `uv run relaymd orchestrator up`.

Start:

```bash
./deploy/tmux/start-orchestrator.sh
```

Attach:

```bash
tmux attach -t relaymd
```

Stop:

```bash
tmux kill-session -t relaymd
```

Logs are visible in the tmux session output.

## Dashboard Access

By default the orchestrator should listen on `127.0.0.1:36158`, not `0.0.0.0`, so the UI/API are not exposed on every interface of a shared login node.

For solo use, the recommended setup is:

1. run `relaymd orchestrator up`
2. run the basic-auth dashboard proxy on `127.0.0.1:36159`
3. forward only port `36159` to your laptop

Start the proxy manually:

```bash
export RELAYMD_API_TOKEN=<relaymd-api-token>
export RELAYMD_DASHBOARD_USERNAME=<username>
export RELAYMD_DASHBOARD_PASSWORD=<password>
uv run relaymd orchestrator proxy
```

Or via tmux:

```bash
export RELAYMD_API_TOKEN=<relaymd-api-token>
export RELAYMD_DASHBOARD_USERNAME=<username>
export RELAYMD_DASHBOARD_PASSWORD=<password>
./deploy/tmux/start-dashboard-proxy.sh
```

Then forward only `36159` in VS Code and open the forwarded URL. The browser will prompt for the basic-auth credentials before the dashboard is served.

The proxy injects `RELAYMD_API_TOKEN` upstream, so the browser does not need to store or manually enter the RelayMD API token.

This does not make the service impossible for other users on the same node to probe, but it prevents them from seeing the dashboard without the proxy credentials.

## Frontend Build

The operator UI is a React app in `frontend/` served by the orchestrator on port `36158`.

Build it before starting or restarting the orchestrator:

```bash
cd frontend
npm --cache ./.npm install
npm --cache ./.npm run build
```

Keep npm cache and build output inside the repo. `frontend/dist/` is generated locally and is not committed.

## Rollout Order

Use this upgrade sequence for compatibility:
1. deploy orchestrator first
2. deploy worker image second
3. upgrade CLI binaries last
