# Checkpoint Handoff Dummy Test

Purpose: validate worker handoff with checkpoint continuity by cancelling one worker mid-run and confirming the next worker resumes from the uploaded checkpoint instead of restarting from iteration 0.

## Bundle contents

- `run.sh`: writes `checkpoint.chk` once per minute for a configurable number of iterations and resumes from `../latest` if the worker downloads a prior checkpoint during reassignment.
- `relaymd-worker.json`: runs `bash run.sh` and configures `checkpoint_glob_pattern` as `*.chk`.

## Local test config

When `relaymd` is run from `./test`, `test/relaymd-config.yaml` already sets:

- `worker_checkpoint_poll_interval_seconds: 60`

That keeps worker-side checkpoint polling aligned with this dummy job so at least two checkpoint uploads should appear before cancelling worker #1.

## Submit

Run from the repository root:

```bash
cd test
source env.sh
uv run relaymd submit checkpoint-handoff --title "checkpoint-handoff"
```

## What to expect

- Worker #1 starts from iteration `0` and writes `checkpoint.chk` every 60 seconds.
- After at least two checkpoint uploads, cancel worker #1.
- The orchestrator should preserve `latest_checkpoint_path` while re-queuing the job.
- Worker #2 should download the prior checkpoint as `../latest`.
- The dummy script should log `resuming from checkpoint iteration <n>` and continue at iteration `<n + 1>`, not restart from `0`.
- The job should complete normally after the resumed worker finishes the remaining iterations.
