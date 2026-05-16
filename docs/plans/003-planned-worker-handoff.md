# Plan 003: Planned Worker Handoff

## Goal
Make wall-time worker exits explicit, clean, and resumable by introducing a planned `handoff` job state and worker API flow that requeues the logical job before Slurm `SIGTERM` becomes the primary shutdown path.

## Scope
- Add first-class `handoff` job status and worker endpoints for handoff start/complete.
- Add proactive SLURM deadline handoff using wrapper-injected deadline environment variables.
- Make checkpoint manifest sync non-destructive when watched files are missing.
- Keep existing `SIGTERM` and stale-worker cleanup as fallback behavior.
- Do not redesign checkpoint manifest storage beyond the no-delete policy needed for resumable checkpoint safety.

## Locked Decisions
1. `handoff` means a planned end to a resume segment where RelayMD stops the payload, preserves resumable checkpoint state, and makes the logical job eligible for another worker.
2. Missing files during checkpoint sync are not evidence that files should be deleted from resumable checkpoint state.
3. Planned allocation end uses `running -> handoff -> queued`.
4. `handoff/start` records intent and current progress, but does not claim a final checkpoint exists.
5. `handoff/complete` atomically records final checkpoint observation and requeues the job.
6. `handoff/complete` can requeue from the previous resumable checkpoint state when no newer valid checkpoint was produced.
7. The worker deregisters and exits `0` after successful `handoff/complete`.
8. The orchestrator requeues on `handoff/complete`, not on worker deregistration.
9. Do not requeue at `handoff/start`; the old worker may still be stopping the payload and uploading checkpoint state.
10. Completion and failure remain payload outcomes; worker allocation end must not be reported as `completed` or `failed`.
11. SLURM wrappers inject deadline configuration; the Python worker remains scheduler-agnostic.
12. Default proactive handoff starts 600 seconds before the allocation deadline.
13. Existing `#SBATCH --signal=TERM@300` remains as a fallback guard.
14. Salad does not get proactive handoff in the first implementation unless a reliable deadline is available.

## API Contract Changes
Add shared models in `relaymd-core`:

- `JobStatus.handoff`
- `HandoffStart`
  - `reason: str`
  - `progress: float | None`
  - `progress_codes: list[str]`
  - `deadline_epoch_seconds: float | None`
  - `message: str | None`
- `HandoffComplete`
  - `checkpoint_manifest_path: str | None`
  - `checkpoint_path: str | None`
  - `progress: float | None`
  - `progress_codes: list[str]`
  - `checkpoint_cycle_status: str | None`
  - `checkpoint_cycle_failures: list[dict[str, str]]`

Add worker endpoints:

- `POST /jobs/{job_id}/handoff/start`
  - Allowed from `running`.
  - Transitions job to `handoff`.
  - Appends `handoff_started` history event with reason, progress, deadline, and message.
- `POST /jobs/{job_id}/handoff/complete`
  - Allowed from `handoff`.
  - If a checkpoint path is supplied, records it like `report_checkpoint`.
  - If no checkpoint path is supplied, preserves the existing latest checkpoint manifest path and records the final cycle status/failures.
  - Transitions job to `queued`, clears `assigned_worker_id`, and appends `handoff_completed` history event.

## State Machine Changes
- Add `JobStatus.handoff`.
- Add allowed transitions:
  - `running -> handoff`
  - `handoff -> queued`
  - `handoff -> cancelled`
- Keep checkpoint updates valid for `assigned`, `running`, `cancelling`, and `handoff`.
- Treat `handoff` as an active segment for history/runtime purposes until `handoff_completed` closes the segment.
- Keep `complete` and `fail` invalid from `handoff` unless a later design explicitly supports that edge case.

## Worker Behavior
1. Read optional env vars:
   - `RELAYMD_ALLOCATION_DEADLINE_EPOCH_SECONDS`
   - `RELAYMD_PROACTIVE_HANDOFF_MARGIN_SECONDS`
2. If both are valid, compute handoff trigger time as `deadline - margin`.
3. During the main job loop, when the trigger time is reached:
   - Read current progress.
   - Call `handoff/start` with `reason="allocation_deadline"`.
   - Request graceful payload termination.
   - Wait for the payload using existing process wait settings.
   - Run a final non-destructive checkpoint manifest cycle.
   - Upload checkpoint status and report final checkpoint observation through `handoff/complete`.
   - Deregister the worker.
   - Exit the process with status code `0`.
4. If `handoff/start` or `handoff/complete` fails transiently, prefer retrying within the remaining margin rather than falling through to payload completion/failure.
5. If proactive handoff env vars are absent or invalid, preserve current behavior.

## SLURM Wrapper Behavior
- Compute or query the active allocation deadline before `apptainer exec`.
- Prefer querying Slurm's live view when available:
  - `squeue -j "$SLURM_JOB_ID" -h --Format=EndTime`
  - or equivalent `scontrol show job "$SLURM_JOB_ID"` parsing if that is more reliable on the cluster.
- Export into the container:
  - `RELAYMD_ALLOCATION_DEADLINE_EPOCH_SECONDS`
  - `RELAYMD_PROACTIVE_HANDOFF_MARGIN_SECONDS`
- Default `RELAYMD_PROACTIVE_HANDOFF_MARGIN_SECONDS` to `600`.
- Keep `#SBATCH --signal=TERM@300` as fallback.
- If deadline detection fails, log a warning and omit the deadline env var so the worker uses existing fallback behavior.

## Checkpoint Sync Changes
- Remove delete-on-missing behavior from `_sync_checkpoint_manifest_cycle`.
- Remove or replace `checkpoint_file_deleted` semantics; missing from the current watch scan should not remove entries from `manifest["files"]`.
- Keep updating entries for files that are observed and safely uploaded.
- Keep failure diagnostics for files that are matched but disappear while being processed.
- Add a cycle summary field only if useful for observability; do not use it as deletion policy.

## Frontend and CLI Behavior
- Include `handoff` in status rendering and filters wherever job status is enumerated.
- Present `handoff` as an active transient state, not terminal and not queued.
- Existing job list/export fields should continue to show progress, checkpoint status, and latest checkpoint path during handoff.
- CLI should tolerate and display `handoff` in list/export output.

## Documentation Changes
- `CONTEXT.md` already defines:
  - `handoff`
  - `resumable checkpoint state`
- ADR:
  - `docs/adr/0003-planned-worker-handoff.md`
- Update after implementation:
  - `docs/job-lifecycle.md`
  - `docs/worker-internals.md`
  - `docs/architecture.md`
  - `deploy/config.example.yaml`

## Implementation Sequence
1. Add shared models/status enum and backend transition methods.
2. Add orchestrator `handoff/start` and `handoff/complete` routes with history events.
3. Update runtime/history logic to treat `handoff` as an active segment that closes on requeue.
4. Regenerate the API client with `./scripts/generate_api_client.sh`.
5. Extend worker gateway with `start_handoff` and `complete_handoff`.
6. Remove destructive manifest deletion from checkpoint sync and update tests.
7. Add worker proactive deadline parsing and handoff trigger logic.
8. Update SLURM template/config defaults to inject deadline and margin env vars.
9. Update frontend/CLI status handling for `handoff`.
10. Update docs and run graphify update.

## Validation Plan
- Backend test: `running -> handoff -> queued` clears `assigned_worker_id` and preserves latest checkpoint path.
- Backend test: `handoff/start` records progress, reason, deadline, and a history event.
- Backend test: `handoff/complete` with a new checkpoint records checkpoint metadata then requeues.
- Backend test: `handoff/complete` with no new checkpoint requeues from the previous latest checkpoint.
- Backend test: checkpoint reports are accepted while status is `handoff`.
- Worker test: proactive deadline triggers `handoff/start`, final checkpoint sync, `handoff/complete`, deregister, and no `complete_job`/`fail_job`.
- Worker test: missing watched files do not delete existing manifest entries across repeated sync cycles.
- Worker test: shutdown/SIGTERM fallback remains non-destructive.
- SLURM template test: deadline and proactive handoff margin env vars are exported when deadline detection succeeds.
- Frontend/CLI tests: `handoff` status renders without falling into unknown/error states.

## Rollout Notes
- This changes API models and requires regenerating the generated API client.
- This changes source and operator docs, so the PR must include the repository-required version bump before push.
- Preserve fallback behavior for workers launched without deadline env vars so non-SLURM deployments are not blocked.
