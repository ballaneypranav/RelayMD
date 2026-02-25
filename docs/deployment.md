# Orchestrator Persistent Deployment

Use a persistent process manager for the orchestrator. A shell-owned process is not production-safe because it dies when the terminal disconnects.

## Path Selection

- Choose **systemd user service** when your host supports `loginctl enable-linger $USER`.
  - Why: auto-start on reboot, auto-restart on failure, standard logging with `journalctl`.
- Choose **tmux fallback** on environments (for example some HPC login nodes) where user lingering is not available.
  - Why: easy manual recovery and keeps the process detached from your SSH session.

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

## systemd User Service (Preferred)

Unit file is at `deploy/systemd/relaymd-orchestrator.service`.
It launches the orchestrator with `uv run relaymd-orchestrator`.

Install and start:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/relaymd-orchestrator.service ~/.config/systemd/user/relaymd-orchestrator.service
systemctl --user daemon-reload
systemctl --user enable relaymd-orchestrator
systemctl --user start relaymd-orchestrator
loginctl enable-linger "$USER"
```

Logs:

```bash
journalctl --user -u relaymd-orchestrator -f
```

Health check:

```bash
curl -i http://127.0.0.1:8000/healthz
```

Expected result: HTTP `200 OK`.

## tmux Fallback

Launcher script is at `deploy/tmux/start-orchestrator.sh`.
It launches the same command: `uv run relaymd-orchestrator`.

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
