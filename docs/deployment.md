# Orchestrator Persistent Deployment

Use tmux for persistent orchestrator processes. A shell-owned process is not production-safe because it dies when the terminal disconnects.

## YAML Config Template

Create `~/.config/relaymd/config.yaml` from the canonical template:

```bash
mkdir -p ~/.config/relaymd
cp deploy/config.example.yaml ~/.config/relaymd/config.yaml
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
