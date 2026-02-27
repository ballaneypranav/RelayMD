# Sleep-5m Worker Smoke Test

Purpose: validate worker registration, job assignment, and heartbeats without checkpoint traffic.

## Bundle contents

- `run.sh`: prints start/end timestamps and sleeps for 300 seconds.
- `relaymd-worker.json`: points worker to `bash run.sh` and uses a checkpoint glob that will not match any file.

## Submit

```bash
uv run relaymd submit test/sleep-5m --title "sleep-5m-smoke"
```

## What to expect

- Worker registers and starts heartbeats (default every 60s).
- Job is assigned and runs for ~5 minutes.
- No `POST /jobs/{id}/checkpoint` calls should occur.
- Job should transition to `completed` when `run.sh` exits.
