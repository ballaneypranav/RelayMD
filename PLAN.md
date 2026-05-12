## Job History + Worker Runtime Timeline (Single PR)

### Summary
Implement persistent, orchestrator-authored job history and expose it in the operator frontend so each job shows a timeline of what happened since submission, including worker handoffs and runtime per worker.  
History is authoritative for new events going forward; existing jobs can show derived minimal history when persisted events are absent.

### Key Implementation Changes
- **Data model + persistence**
  - Add append-only `job_event` storage with typed core fields (`job_id`, `occurred_at`, per-job `event_seq`, `event_type`, `worker_id`, `status_from`, `status_to`) and optional `payload_json`.
  - Add startup migration in orchestrator DB init to create/upgrade `job_event` table and indexes (`job_id`, `occurred_at`, `event_seq`), matching current in-place migration pattern.
  - Define a validated event-type set (stored as strings): `created`, `assigned`, `running`, `checkpoint`, `requeued_with`, `requeued_from`, `completed`, `failed`, `cancelled`, `worker_deregistered_requeue`.

- **Event capture (strict atomic with job updates)**
  - Emit `job_event` rows in the same DB transaction as lifecycle mutations so status changes cannot commit without corresponding history.
  - Capture events at all orchestrator write points: job creation, assignment success, start, checkpoint report, terminal transitions, cancel, and requeue paths.
  - Requeue behavior:
    - old job gets `requeued_with=<new_job_id>`
    - new job gets `requeued_from=<old_job_id>`
  - For checkpoint events, persist progress/progress-codes/checkpoint status-failure metadata in payload for auditability.

- **History read API**
  - Add `GET /jobs/{job_id}/history` returning:
    - `events` (ordered by `occurred_at`, tie-broken by `event_seq`)
    - `worker_segments` (start/end/running duration segments)
    - `worker_totals` (total runtime and segment count per worker)
  - Runtime semantics:
    - segment start = `running` when present, else `assigned`
    - segment end = next assignment to different worker, terminal event, or `now` for active jobs
    - terminal event is authoritative cutoff for runtime accounting.
  - If no persisted events exist (legacy jobs), synthesize minimal derived timeline from current job fields with `derived=true`.

- **Frontend UI**
  - Extend frontend API/types to consume `/jobs/{id}/history`.
  - In selected job detail pane, add:
    - timeline view (timestamp, event, worker, key details)
    - worker runtime summary table
    - pinned “Latest issues” panel for current failures/codes
  - Collapse successful checkpoint events by default with expand control; failures remain prominently visible.
  - Keep this feature in detail pane only (no jobs-table indicator in v1).

- **Schema/client updates**
  - Add shared read models for job history/event payloads and update OpenAPI.
  - Regenerate `relaymd-api-client` from OpenAPI once backend schema/routes are complete.
  - Ensure frontend type contracts align with generated/read models.

### Test Plan
- **Orchestrator/DB**
  - Migration creates `job_event` table/indexes on clean and existing DBs.
  - Event write is atomic with lifecycle updates (failure in event insert prevents transition commit).
  - `event_seq` monotonic ordering per job, including same-timestamp events.
- **Lifecycle/history behavior**
  - Events emitted for create/assign/start/checkpoint/terminal/cancel/requeue.
  - Requeue writes both `requeued_with` and `requeued_from` entries with correct job IDs.
  - History endpoint ordering, payload shape, and derived-history fallback for legacy jobs.
  - Runtime calculations for:
    - single-worker run
    - worker handoff(s)
    - running-without-terminal (open segment to now)
    - assigned-without-running fallback
- **Frontend**
  - Job detail renders timeline and worker totals.
  - Checkpoint success collapse/expand behavior works.
  - Latest issues panel shows failures/codes and handles empty state.

### Assumptions and Defaults
- Scope is orchestrator-only history (not worker-local log timelines).
- No pruning for `job_event` in this iteration.
- History view is per-job only (no cross-job lineage stitching), but requeue link events are persisted for future lineage features.
- Paths/details are included in history payload with defensive sanitization/truncation for obviously sensitive strings.
- Delivery is a single PR containing schema, backend, frontend, and tests.

## Frontend Runtime + ETA Additions

### Summary
Extend the frontend job detail view to show total running time and estimated time remaining (ETA) derived from job history runtime segments plus current progress.

### Key Implementation Additions
- **Runtime source and semantics**
  - Compute `total_runtime_seconds` from history worker segments (sum of all running durations across workers).
  - Use `running` segment starts when available; fallback to `assigned` starts when no running segment exists.
  - For active jobs, treat open segment end as `now` on each refresh tick.
  - For terminal jobs, freeze total runtime at terminal-event cutoff.

- **ETA calculation**
  - Use linear estimate with latest progress value:
    - `estimated_total_seconds = total_runtime_seconds / progress`
    - `eta_seconds = estimated_total_seconds - total_runtime_seconds`
  - Use latest reported progress directly (regressions are accepted and can increase ETA).
  - Frontend defensively clamps progress to `[0,1]` before ETA math.
  - Hide ETA when:
    - job is not `assigned`/`running`, or
    - progress `<= 0`, or
    - progress `>= 1`.

- **UI placement and formatting**
  - Add `Total Runtime` and `ETA` to selected job detail pane (no jobs-table column in this iteration).
  - Format both via existing compact duration formatter (e.g., `2h 13m`, `14m 20s`).
  - For `assigned` jobs with no started/runtime segment, show `Total Runtime = 0m 0s` and hide ETA.

### Test Plan Additions
- **Frontend unit/integration tests**
  - Runtime sum across single-worker and multi-worker segment histories.
  - Open running segment grows with current time.
  - Terminal jobs show stable total runtime and hidden ETA.
  - ETA hidden cases: progress `0`, progress `1`, and non-active statuses.
  - ETA updates upward when progress regresses.
  - Out-of-range progress values are clamped before calculation.

### Assumptions and Defaults
- No progress threshold guard before showing ETA in this iteration.
- No extra ETA label/caveat text is required in the UI.
- Runtime/ETA rely on history endpoint segment data as source of truth.
