# Implement Accurate Job Lifecycle Status Reporting

## Summary
Create a new branch from clean `main`, implement explicit job lifecycle timestamps, add the missing worker “start/running” transition, and update the frontend so `Time In Status` no longer resets on checkpoint uploads. Branch name: `fix/job-lifecycle-status-reporting`. Version bump: `0.1.45 -> 0.1.46` via the repo release workflow.

## Key Changes
- Add lifecycle fields to the shared `Job` / `JobRead` model:
  - `assigned_at: datetime | None`
  - `started_at: datetime | None`
  - `status_changed_at: datetime`
  - Keep `updated_at` as generic “last row update”.
- Add an automatic startup migration/backfill path for existing DBs:
  - Add missing columns if absent.
  - Backfill `status_changed_at` from `updated_at`.
  - Backfill `assigned_at` from `updated_at` for existing `assigned`/`running` jobs when absent.
  - Leave `started_at` null for historical jobs unless a real running transition occurs.
- Update transitions:
  - Job creation initializes `status_changed_at = created_at = updated_at`.
  - Assignment sets `assigned_at`, `status_changed_at`, and `updated_at`.
  - Checkpoint reporting updates only `latest_checkpoint_path`, `last_checkpoint_at`, and `updated_at`; it must not change `status_changed_at`.
  - Terminal/requeue/cancel transitions update `status_changed_at` and `updated_at`.

## Worker Running Transition
- Add worker API endpoint: `POST /jobs/{job_id}/start`, returning `204`.
- It should mark `assigned -> running` through `JobTransitionService.mark_job_running()`.
- Make `/start` idempotent for already-`running` jobs: return `204` without resetting timestamps.
- Regenerate the API client with `./scripts/generate_api_client.sh`.
- Add `start_job(job_id=...)` to the worker gateway and call it immediately after `execution.start()` in `_run_assigned_job()`, so `running` means the workload process was launched.
- Treat `409` conflicts in the worker gateway the same way complete/fail/checkpoint currently do: log and continue, so cancellation races do not crash worker cleanup paths.

## Frontend Reporting
- Update frontend `JobRead` type to include `assigned_at`, `started_at`, and `status_changed_at`.
- Table columns:
  - `Age`: `now - created_at`
  - `Time In Status`: `now - status_changed_at`
  - `Checkpoint`: `now - last_checkpoint_at`
- Job detail panel:
  - Keep `Created` and `Updated`.
  - Add `Assigned`, `Started`, and `Status Changed`.
  - Optionally show `Runtime` as `now - started_at` when `started_at` exists.
- Preserve existing action behavior: queued/assigned/running remain cancellable; failed/cancelled remain re-queueable.

## Tests
- Orchestrator tests:
  - Worker flow: request leaves job `assigned`; `/jobs/{id}/start` marks it `running`; checkpoint does not change `status_changed_at`; complete marks terminal status and advances `status_changed_at`.
  - `/start` on an already-running job is idempotent and does not reset `started_at`/`status_changed_at`.
  - Existing DB migration/backfill adds lifecycle columns and preserves readable jobs.
- Worker tests:
  - `_run_assigned_job()` calls `gateway.start_job()` after `execution.start()` and before checkpoint/completion reporting.
  - Existing failure/cancellation tests account for the new start call where execution actually begins.
- Frontend tests:
  - `buildJobRows()` uses `status_changed_at` for `time_in_status`.
  - Checkpoint age remains based on `last_checkpoint_at`.
  - App fixture data includes the new lifecycle fields.
- Validation commands:
  - `uv run pytest tests/orchestrator packages/relaymd-worker/tests`
  - `uv run pytest tests/cli`
  - `uv run ruff check .`
  - `uv run pyright`
  - `cd frontend && npm --cache ./.npm run build && npm --cache ./.npm test`

## Branch, Release, and Graph
- Start with:
  - `git switch -c fix/job-lifecycle-status-reporting`
- After implementation and tests, run:
  - `make release-cli VERSION=0.1.46`
- Because code files changed, run:
  - `graphify update .`
- Final branch should include source changes, generated API client updates, tests, graph update output if it modifies tracked graph artifacts, and the `v0.1.46` release commit/tag created by the release target.
