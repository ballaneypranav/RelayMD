# W-194 E2E Test Report

## Summary

- Linear issue: `W-194`
- Validation target: checkpoint upload and persistence with dummy workload
- Bundle used: `test/checkpoint-test`
- Job ID: `2543fbb2-8ecc-4a6b-80d0-487da97d2130`
- Result: passed

This run validated that the dummy workload rewrote `checkpoint.chk` during execution, the worker uploaded checkpoints to B2, the orchestrator persisted `latest_checkpoint_path`, and that checkpoint metadata remained present through normal job completion.

## Test Setup

- RelayMD orchestrator running on `http://127.0.0.1:36158`
- Worker bootstrap orchestrator URL from Infisical:
  `http://relaymd-orchestrator:36158`
- Dummy bundle:
  - `run.sh` writes `checkpoint.chk` immediately, then rewrites it every 60 seconds for 5 total iterations
  - `relaymd-worker.json` sets `checkpoint_glob_pattern` to `*.chk`
- Local test config:
  - `worker_checkpoint_poll_interval_seconds: 60`

## Evidence

### Worker execution

Relevant worker log excerpt:

```text
relaymd checkpoint test start: 2026-03-30T22:32:27Z
hostname: gilbreth-g004.rcac.purdue.edu
writing checkpoint.chk 5 times every 60s
checkpoint write 1/5: 2026-03-30T22:32:27Z
checkpoint write 2/5: 2026-03-30T22:33:27Z
```

Worker bootstrap also showed the correct orchestrator target:

```text
"orchestrator_url":"http://relaymd-orchestrator:36158"
```

### Axiom evidence

Dataset: `relaymd`

Observed structured events for job `2543fbb2-8ecc-4a6b-80d0-487da97d2130`:

- First `checkpoint_recorded`: `2026-03-30T22:56:44.292130Z`
- Additional `checkpoint_recorded` events:
  - `2026-03-30T22:57:44.353373Z`
  - `2026-03-30T22:58:44.593176Z`
  - `2026-03-30T22:59:44.435763Z`
  - `2026-03-30T22:59:46.518940Z`
- `job_completed_reported`: `2026-03-30T22:59:46.547695Z`

Persisted checkpoint path in orchestrator state:

```text
jobs/2543fbb2-8ecc-4a6b-80d0-487da97d2130/checkpoints/latest
```

This shows:

- `latest_checkpoint_path` became non-null after checkpoint upload/report
- checkpoint metadata was updated multiple times during execution
- checkpoint metadata remained present immediately before completion

### B2 evidence

Backblaze B2 browser path:

```text
saladcloud-test/jobs/2543fbb2-8ecc-4a6b-80d0-487da97d2130/checkpoints
```

Observed object listing:

```text
latest (5)    410.0 bytes    03/30/2026 18:59
```

This confirms the checkpoint object exists in B2 at:

```text
jobs/2543fbb2-8ecc-4a6b-80d0-487da97d2130/checkpoints/latest
```

## Definition of Done Check

- [x] Checkpoint file written by dummy subprocess appears in B2
- [x] Orchestrator DB `latest_checkpoint_path` is non-null after first upload
- [x] `latest_checkpoint_path` is preserved on job completion
- [x] Validation evidence captured with B2 listing, log excerpts, and timestamps
- [ ] Commit message and PR include `fixes W-167b`

## Issues Found

No functional checkpoint persistence issues were found in this validation run.

Operational notes observed during setup:

- A stale `RELAYMD_ORCHESTRATOR_URL` value in Infisical caused workers to target port `8000` until updated to `36158`.
- Local shell/UI overrides also caused temporary confusion when `RELAYMD_ORCHESTRATOR_URL` still pointed to `8001`.

These were environment/config synchronization issues rather than checkpoint pipeline failures.

## Conclusion

W-194 runtime validation succeeded. The dummy workload produced checkpoints, RelayMD uploaded them to B2, the orchestrator persisted `latest_checkpoint_path`, and that checkpoint metadata remained present through successful job completion.
