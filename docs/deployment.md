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
