# Orchestrator Persistent Deployment

Use a persistent process manager for the orchestrator. A shell-owned process is not production-safe because it dies when the terminal disconnects.

## Path Selection

- Choose **systemd user service** when your host supports `loginctl enable-linger $USER`.
  - Why: auto-start on reboot, auto-restart on failure, standard logging with `journalctl`.
- Choose **tmux fallback** on environments (for example some HPC login nodes) where user lingering is not available.
  - Why: easy manual recovery and keeps the process detached from your SSH session.

## Environment File Template

Create `~/.config/relaymd/.env`:

```env
DATABASE_URL=sqlite+aiosqlite:////srv/relaymd/orchestrator/relaymd.db
RELAYMD_API_TOKEN=change-me
B2_ENDPOINT_URL=https://s3.us-west-000.backblazeb2.com
B2_BUCKET_NAME=relaymd-bucket
B2_ACCESS_KEY_ID=your-key-id
B2_SECRET_ACCESS_KEY=your-secret-access-key
SLURM_CLUSTER_CONFIGS=[]
```

SQLite recommendation: keep the database in a stable persistent directory (for example `/srv/relaymd/orchestrator/relaymd.db`), not `/tmp`.

## systemd User Service (Preferred)

Unit file is at `deploy/systemd/relaymd-orchestrator.service`.

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
