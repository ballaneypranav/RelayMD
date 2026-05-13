# Frontend Runtime Cancel/Requeue Behavior

## Goal

Implement truthful cancellation semantics for RelayMD jobs cancelled from the frontend/API.

Cancellation should not merely hide a job or flip it directly to a terminal state while compute may still be running. For assigned or running jobs, cancellation becomes a request that the worker observes, stops the current job process, performs best-effort checkpoint/log cleanup, and then asks the orchestrator for more work. The orchestrator marks the job `cancelled` only when the worker has effectively moved on or is dead.

## Agreed Semantics

- Queued, unassigned jobs cancel immediately: `queued -> cancelled`.
- Assigned or running jobs transition to `cancelling`, not directly to `cancelled`.
- A `cancelling` job becomes `cancelled` when either:
  - the assigned worker next calls `/jobs/request`, or
  - the assigned worker deregisters, is reaped as stale, or otherwise disappears.
- Cancellation targets the job process, not the worker allocation. A healthy worker should stop the cancelled job, then request another matching job and continue according to its normal idle strategy.
- If no matching job is available after cancellation, existing worker idle behavior applies. With `immediate_exit`, the worker exits; with `poll_then_exit`, it polls until timeout.
- Running-job cancellation should remain explicit in the UI/API, equivalent to the current `force=true` behavior.
- Cancelled jobs are terminal. Late worker reports for a `cancelling` or `cancelled` job must not turn it into `completed` or `failed`.
- Cancellation should preserve latest checkpoint metadata. The worker should make a bounded best-effort checkpoint/status/log upload before terminating the process.

## State Model

Add a new job status:

```text
queued -> cancelled
assigned -> cancelling -> cancelled
running -> cancelling -> cancelled
```

Keep existing terminal statuses:

```text
completed
failed
cancelled
```

`cancelling` is non-terminal and counts as an active/busy status for worker assignment.

## API Behavior

### Operator Cancel

Update the existing operator cancel endpoint:

- `DELETE /jobs/{job_id}` for `queued` jobs:
  - transition to `cancelled`
  - clear `assigned_worker_id`
  - append `cancelled` history event
- `DELETE /jobs/{job_id}?force=true` for `assigned` or `running` jobs:
  - transition to `cancelling`
  - preserve `assigned_worker_id`
  - set `cancellation_requested_at`
  - append `cancel_requested` history event
- `DELETE /jobs/{job_id}` for `running` without `force=true`:
  - keep the current conflict behavior

### Worker Request

Update `/jobs/request` so that, before assigning a new job to the requesting worker, it finalizes any job assigned to that worker with status `cancelling`:

- transition `cancelling -> cancelled`
- clear `assigned_worker_id`
- append `cancelled` history event
- then continue normal matching assignment in the same request flow

This endpoint is the worker acknowledgement boundary.

### Worker Complete/Fail/Checkpoint

Update worker job mutation endpoints:

- `complete` for `cancelling` or `cancelled`: return conflict or no-op, but do not mark completed.
- `fail` for `cancelling` or `cancelled`: return conflict or no-op, but do not mark failed.
- `checkpoint` for `cancelling`: allow best-effort checkpoint metadata updates if useful, because the worker may be saving state during cancellation cleanup.

## Worker Behavior

The worker should observe cancellation while handling a job.

Recommended first implementation:

- Add a lightweight worker-facing control endpoint, for example `GET /jobs/{job_id}/control`, returning whether cancellation is requested.
- Poll this control endpoint in the existing execution/checkpoint loop.
- Check cancellation before starting user code, after bundle download/hydration, and during long-running execution polling.
- When cancellation is observed:
  - request graceful termination of the user process
  - wait up to a bounded cancellation checkpoint grace period
  - upload latest checkpoint/status/logs if available
  - kill the process if it has not exited
  - return from `_run_assigned_job` without calling `complete` or `fail`
  - loop back to `/jobs/request`, which finalizes the previous job as `cancelled` and may assign another matching job

Reuse existing shutdown/checkpoint mechanics where possible rather than creating a separate process-control path.

## Worker Liveness And Reaping

Update stale worker/deregister/orphan handling:

- If a worker deregisters with a `cancelling` job, mark that job `cancelled`, not `queued`.
- If stale worker reaping finds a `cancelling` job, mark that job `cancelled`, not `queued`.
- If orphaned job requeue logic sees a `cancelling` job with no live assigned worker, mark it `cancelled`, not `queued`.
- `cancelling` jobs should be treated as active/busy while the worker is still alive.

## Scheduling And Provisioning

- Include `cancelling` in active job statuses for worker busy checks.
- Do not count `cancelling` jobs as queued demand for SLURM provisioning or Salad autoscaling.
- Existing preferred cluster matching remains unchanged for subsequent assignments.
- A worker that cancels a pinned job may receive another job only if the normal cluster matching rules allow it.

## Frontend Behavior

Expose `cancelling` distinctly from `cancelled`.

Recommended UI behavior:

- Queued jobs: show `Cancel`; result becomes `cancelled` immediately.
- Assigned/running jobs: show a confirmation for runtime cancellation.
- After confirmation: show `cancelling` until the worker requests another job or dies.
- Terminal `cancelled` means RelayMD has observed that the worker moved on or the worker disappeared.

## Data Model Changes

Likely changes:

- Add `JobStatus.cancelling` to shared core enum.
- Add DB migration for enum/string compatibility if needed.
- Add optional `Job.cancellation_requested_at`.
- Optionally add `Job.cancelled_at` if useful for UI/history; otherwise status history can supply this.
- Regenerate API client after OpenAPI schema changes.

## Manual Requeue Checkpoint Manifest Compatibility

Frontend/API requeue of a terminal job should keep creating a new job ID. The
new job is an audit/history clone, not an in-place resurrection of the old
terminal row.

Checkpoint resume semantics for cloned jobs:

- Preserve the old job's input bundle path on the new queued job.
- Preserve the old job's checkpoint manifest reference on the new queued job.
- When the new job is assigned, the worker should download and hydrate
  checkpoint files from the preserved old manifest.
- The worker must not edit, overwrite, or append to the old job's checkpoint
  files or manifest.
- After hydration, all new checkpoint files, status files, and manifests belong
  under the new job ID.
- If the preserved manifest is missing or unreadable, the new job should fail
  rather than silently restart from scratch.

Rename checkpoint metadata to make the contract explicit:

- Rename `latest_checkpoint_path` to `latest_checkpoint_manifest_path` in the DB
  and shared API models.
- Rename worker checkpoint reports from `checkpoint_path` to
  `checkpoint_manifest_path`.
- Apply the DB migration as a column rename so existing values are preserved.
- Treat existing stored values as manifest keys; no data transformation is
  expected.

Rolling compatibility is required because already-rendered SLURM jobs and
already-running workers may still use the old generated client:

- `/jobs/request` should temporarily return both
  `latest_checkpoint_manifest_path` and deprecated `latest_checkpoint_path`.
- `/jobs/{job_id}/checkpoint` should temporarily accept both
  `checkpoint_manifest_path` and deprecated `checkpoint_path`.
- New worker code should prefer the new fields but tolerate old fields.
- Add a follow-up TODO to remove deprecated checkpoint field aliases after all
  deployed workers and pending SLURM allocations are known to be on the new
  release.

## History Events

Add/standardize events:

- `cancel_requested`: operator requested runtime cancellation; status becomes `cancelling`.
- `cancelled`: cancellation finalized; status becomes `cancelled`.

Preserve existing requeue events.

## Test Plan

### Orchestrator Unit/Endpoint Tests

- Queued job cancellation still transitions directly to `cancelled`.
- Assigned job cancellation transitions to `cancelling`, preserves `assigned_worker_id`, and records `cancel_requested`.
- Running job cancellation without force returns conflict.
- Running job cancellation with force transitions to `cancelling`, preserves `assigned_worker_id`, and records `cancel_requested`.
- `/jobs/request` by the assigned worker finalizes `cancelling -> cancelled`, clears assignment, records `cancelled`, and then assigns the next matching queued job.
- `/jobs/request` by a different worker does not finalize another worker's `cancelling` job.
- Worker complete/fail cannot convert `cancelling` or `cancelled` jobs to completed/failed.
- Checkpoint reporting for `cancelling` is accepted if checkpoint metadata preservation is implemented.
- Stale worker reaper finalizes `cancelling` jobs to `cancelled`.
- Worker deregistration finalizes `cancelling` jobs to `cancelled`.
- `cancelling` jobs count as busy for assignment.
- `cancelling` jobs do not count as queue demand for provisioning.

### Worker Tests

- Worker checks cancellation before launching user process.
- Worker detects cancellation during execution polling.
- Worker performs best-effort checkpoint/status/log upload on cancellation.
- Worker terminates then kills the process after timeout if needed.
- Worker does not call `complete` or `fail` after cancellation cleanup.
- Worker loops back to `/jobs/request` after cancellation cleanup.
- If another matching job is returned, worker starts it normally.
- If no job is returned, existing idle strategy behavior applies.

### Frontend Tests

- `cancelling` status renders distinctly.
- Running cancel flow requires confirmation/force.
- Cancelled terminal state remains visible and is not confused with hidden/deleted jobs.

## Implementation Order

1. Add core status/model fields and migration.
2. Update transition service and history event allowlists.
3. Update operator cancel endpoint to use `cancelling` for assigned/running jobs.
4. Update assignment service `/jobs/request` path to finalize assigned `cancelling` jobs before assignment.
5. Update worker lifecycle reaper/deregister/orphan logic for `cancelling`.
6. Add worker control endpoint and generated client updates.
7. Update worker execution loop to poll cancellation and stop user process cleanly.
8. Update frontend status rendering and cancel confirmation behavior.
9. Regenerate API client.
10. Run targeted tests, then full Python/frontend checks if feasible.

## Open Follow-Ups

- Exact cancellation grace timeout name/default.
- Whether to add `cancelled_at` as a denormalized field or rely on job history.
- Whether the worker control endpoint should also return future controls such as pause/resume, or stay cancellation-only for now.
