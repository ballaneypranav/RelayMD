# Checkpoint Upload Dummy Test

Purpose: validate end-to-end checkpoint upload and persistence with a minimal bundle that rewrites `checkpoint.chk` during a normal job run.

## Bundle contents

- `run.sh`: writes `checkpoint.chk` immediately, then rewrites it every 60 seconds for 5 total iterations.
- `relaymd-worker.json`: runs `bash run.sh` and configures `checkpoint_glob_pattern` as `*.chk`.

## Local test config

When `relaymd` is run from `./test`, `test/relaymd-config.yaml` now sets:

- `worker_checkpoint_poll_interval_seconds: 60`

That keeps worker-side checkpoint polling aligned with this dummy job so uploads should occur during execution, not only at process exit.

## Submit

Run from the repository root:

```bash
cd test
source env.sh
uv run relaymd submit checkpoint-test --title "checkpoint-test"
```

## What to expect

- The worker writes `checkpoint.chk` immediately after the job starts.
- The worker should upload at least one checkpoint to `jobs/{job_id}/checkpoints/latest` while the job is still running.
- `relaymd monitor` or `GET /jobs/{id}` should show `latest_checkpoint_path` populated after the first upload.
- The job should complete normally after about 4 minutes.
