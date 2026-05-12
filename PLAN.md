# Storage-Backed Worker Liveness Plan

## Problem

RelayMD currently treats a missing worker heartbeat as evidence that the worker
has died. That is too aggressive for long-running HPC jobs. If Tailscale is
disrupted, the orchestrator host goes offline, or the worker cannot reach the
orchestrator API, the worker may still be running and producing useful
checkpoints. Requeueing in that case wastes compute and can create duplicate
execution.

The design goal is to separate control-plane reachability from job progress
liveness.

## Current Defaults To Reuse

Use existing settings where possible instead of introducing new knobs.

- API heartbeat interval: `heartbeat_interval_seconds = 60`
- API heartbeat stale threshold: `heartbeat_interval_seconds * heartbeat_timeout_multiplier`
- API heartbeat stale threshold with defaults: `60 * 2.0 = 120s`
- Stale worker reaper interval: `stale_worker_reaper_interval_seconds = 60`
- SLURM scheduler interval: `sbatch_submission_interval_seconds = 60`
- Worker checkpoint poll interval: `worker_checkpoint_poll_interval_seconds = 300`
- Proposed storage status stale threshold: `worker_checkpoint_poll_interval_seconds * 6`
- Proposed storage status stale threshold with defaults: `300 * 6 = 1800s`

If a bundle overrides `checkpoint_poll_interval_seconds`, the worker should
write the resolved interval into `status.json`. The orchestrator should prefer
that value for the stale calculation and fall back to
`settings.worker_checkpoint_poll_interval_seconds`.

## Design

Workers should continue writing checkpoint artifacts to storage as they do
today, but each successful checkpoint/status cycle should also update a small
structured status object:

```text
jobs/<job_id>/checkpoints/status.json
```

The current manifest remains the source of checkpoint file inventory:

```text
jobs/<job_id>/checkpoints/manifest.json
```

`status.json` is the storage-backed liveness signal. The orchestrator should use
it as evidence that useful job progress may still be happening even when the
worker API heartbeat is stale.

Example shape:

```json
{
  "schema_version": 1,
  "job_id": "00000000-0000-0000-0000-000000000000",
  "worker_id": "00000000-0000-0000-0000-000000000000",
  "provider_id": "gilbreth:123456",
  "updated_at": "2026-05-12T00:00:00Z",
  "checkpoint_manifest_path": "jobs/<job_id>/checkpoints/manifest.json",
  "checkpoint_poll_interval_seconds": 300,
  "progress": 0.42,
  "progress_codes": ["running"],
  "checkpoint_cycle_status": "success"
}
```

## Orchestrator Behavior

When the worker API heartbeat is fresh, behavior remains unchanged.

When the worker API heartbeat is stale:

1. Do not immediately delete the worker row.
2. Do not immediately requeue assigned or running jobs.
3. If the worker is an HPC worker with a SLURM `provider_id`, query SLURM status
   using the existing `squeue` path.
4. Throttle SLURM status queries using existing `provider_last_checked_at`; a
   reasonable target is the existing API stale threshold, currently about
   `120s`.
5. If SLURM reports the allocation is still running, keep the job status as
   `running` and keep the job assigned to that worker.
6. Read `status.json` from storage when deciding whether job progress is fresh,
   stale, or unknown.
7. If `status.json` is fresh, treat the job as still alive even if API heartbeat
   is stale.
8. If `status.json` is stale but SLURM still reports running, keep the job
   assigned and mark it as progress-stale/unreachable for operator visibility.
9. Requeue only when scheduler/provider state says the allocation is gone,
   failed, cancelled, completed, or otherwise no longer running.

For non-HPC workers, provider state may not be available. In that case,
`status.json` freshness should protect against premature requeue while it is
fresh. Once both API heartbeat and storage status are stale, the existing requeue
behavior can apply.

## SLURM Running But Status Stale

If the API heartbeat is missing, `status.json` has not updated for 30 minutes,
and SLURM reports the allocation is still running:

- Keep the job in `running`.
- Keep the worker/job assigned.
- Mark the condition visibly as progress stale.
- Do not start another worker for the job.
- Do not run `scancel` automatically by default.

Automatic `scancel` is risky because the worker may still be computing useful
state that has not reached storage. The default policy should prefer avoiding
duplicate execution and accidental kills. Add an explicit operator action for
canceling the SLURM allocation, and consider a future opt-in auto-cancel policy
with a much longer timeout.

## Worker Behavior

When the worker cannot reach the orchestrator API:

1. Continue running the assigned job.
2. Continue writing checkpoint files and `manifest.json`.
3. Continue writing `status.json` to storage.
4. Do not terminate the job solely because the orchestrator API heartbeat is
   degraded, provided storage checkpoint/status updates are succeeding.
5. When API connectivity recovers, resume normal heartbeat and checkpoint
   reporting.

The existing worker degraded-mode shutdown should be adjusted so storage-backed
status/checkpoint success keeps the worker alive during orchestrator API outages.

## Data Model Notes

The current `Worker` model already has provider status fields:

- `provider_state`
- `provider_state_raw`
- `provider_reason`
- `provider_last_checked_at`

Reuse these for SLURM status checks instead of adding a parallel polling model.

We may need new worker/job visibility states later, but the first pass can avoid
schema churn by logging and surfacing derived status in API responses. If a
persistent operator-facing state is needed, add it deliberately after the
reaper behavior is correct.

## Implementation Steps

1. Add worker-side `status.json` generation next to checkpoint manifest upload.
2. Include resolved checkpoint poll interval, worker ID, provider ID, progress,
   progress codes, and checkpoint cycle status in `status.json`.
3. Add storage read support in the orchestrator path that evaluates stale
   workers.
4. Rework stale worker reaping so active HPC workers with running SLURM
   allocations are not deleted and their jobs are not requeued.
5. Reuse the existing SLURM `squeue` helper for active workers, not only queued
   placeholders.
6. Update provider status fields from the SLURM query.
7. Requeue assigned/running jobs only when the provider allocation is no longer
   alive, or when no provider exists and both API heartbeat and `status.json`
   are stale.
8. Adjust worker degraded-mode shutdown so successful storage status/checkpoint
   writes extend the grace period during API outages.
9. Add tests for stale heartbeat with fresh `status.json`, stale heartbeat with
   stale `status.json` but running SLURM job, and stale heartbeat with exited
   SLURM job.
10. Document the failure semantics and operator action for manual cancellation.

## Non-Goals

- Do not make the orchestrator scan arbitrary checkpoint files to infer liveness.
- Do not requeue a SLURM-backed job while SLURM reports the allocation is
  running.
- Do not automatically `scancel` progress-stale allocations by default.
- Do not replace the existing checkpoint manifest contract.

