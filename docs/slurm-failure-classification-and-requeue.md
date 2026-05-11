# Slurm Failure Classification for RelayMD Requeue

## Context
This note captures observed behavior from investigating RelayMD job `4c41fc6c-71b2-456c-8ed3-5858593b60a0` and its worker allocations, with focus on deciding when RelayMD should automatically requeue from checkpoint versus mark permanently failed.

## Key Incident Summary
- RelayMD job: `4c41fc6c-71b2-456c-8ed3-5858593b60a0`
- Orchestrator recorded `job_failed_reported` at `2026-05-11T02:42:25Z`.
- Worker log ended with:
  - `forcing final checkpoint write`
  - `skip checkpoint archive: ckpt_is_valid not present`
- No explicit Python traceback in worker output.

### Associated SLURM worker allocation
- SLURM job: `10689989` (derived from worker provider id `gilbreth-a100-40gb:10689989`)
- `sacct` top-level row:
  - `State=COMPLETED`
  - `ExitCode=0:0`
  - `DerivedExitCode=130:0`
  - `Elapsed=23:55:27`
  - `Timelimit=1-00:00:00`
- Step row:
  - `10689989.0` had `State=FAILED`, `ExitCode=130:0`

This is an important edge case: top-level job state looked successful, while step-level state indicated failure.

## What RelayMD Currently Does
Current behavior is status-driven inside worker/orchestrator, not SLURM-aware at failure time:

- Worker reports `fail_job` when execution result is `failed`.
- Orchestrator transitions job to terminal `failed`.
- Auto-requeue logic only requeues jobs in `assigned`/`running` when worker is stale/orphaned.
- Terminal `failed` jobs are not auto-requeued in place.

Implication: any worker-side fail report bypasses orphan/stale requeue paths.

## Available Signals in This Environment
`/usr/bin/sacct` provides useful classification states in this cluster.

Observed examples:
- `TIMEOUT` exists for RelayMD worker job `10691688`.
- Many failures appear as `FAILED` with non-zero step exits.
- Some jobs are `CANCELLED by <uid>`.

### Recommended fields to query
Use:
- `State`
- `Reason`
- `ExitCode`
- `DerivedExitCode`
- `Elapsed`
- `Timelimit`
- step rows (`<jobid>.batch`, `<jobid>.0`, etc.)

Command shape:

```bash
sacct -j <jobid> --format=JobIDRaw,JobID,JobName,State,Reason,ExitCode,DerivedExitCode,Elapsed,Timelimit,Start,End -P
```

## Proposed Classification Model
Given a RelayMD worker fail report, classify SLURM outcome into categories:

### A) Resumable infrastructure/runtime interruption (auto-requeue)
If top-level or relevant step state indicates any of:
- `TIMEOUT`
- `PREEMPTED`
- `NODE_FAIL`
- `BOOT_FAIL`
- `OUT_OF_MEMORY`

Then: requeue from latest checkpoint.

### B) Explicit operator/system cancel (policy-based)
If state is `CANCELLED` (including `CANCELLED by <uid>`):
- if cancellation is system-driven/preemption-like -> optional requeue
- if user/operator initiated -> likely do not requeue

### C) Ambiguous or application failure
Examples:
- `FAILED` with nonzero exit and no infra state
- top-level `COMPLETED` but nonzero `DerivedExitCode` or failed step (like `10689989`)

Then: inspect additional context (worker logs, step exits, checkpoint freshness), and default policy can be:
- conservative: mark failed
- resumability-first: retry limited times from checkpoint, then fail

## Critical Edge Cases
1. Top-level `COMPLETED` is not sufficient to declare success.
2. Step-level failures can carry the real termination semantics.
3. `DerivedExitCode` can reveal hidden failures when top-level `ExitCode` is `0:0`.
4. In some jobs, no explicit timeout marker appears even near time limit; use combined evidence.

## Implementation Outline
1. On worker fail report, if `provider_id` encodes SLURM job id (`<cluster>:<jobid>`), run `sacct` lookup.
2. Parse both top-level and step rows.
3. Map rows to classification buckets above.
4. If classification is resumable interruption, transition to queued/requeue clone instead of terminal failed.
5. Persist classification details on job metadata/logs for observability.

## Suggested Data to Persist per Failed Attempt
- `slurm_job_id`
- `slurm_state_top`
- `slurm_reason_top`
- `slurm_exit_top`
- `slurm_derived_exit_top`
- representative failed step (`jobid.step`, `state`, `exit`)
- `classification` enum (e.g., `timeout`, `node_fail`, `app_fail`, `ambiguous`)
- `requeue_decision` + reason string

## Operational Notes
- `scontrol show job <jobid>` can be useful while job is active.
- For completed jobs, `sacct` is the primary durable source.
- Keep a bounded retry/requeue count to avoid infinite loops on repeated non-progress failures.

## Recommended Next Step
Implement a small classification service in orchestrator that is invoked before finalizing `failed` status, with a feature flag to enable auto-requeue on resumable SLURM states.
