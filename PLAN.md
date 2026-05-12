### Worker Heartbeat Degraded-Mode Resilience Plan

### Summary
Implement degraded-mode handling in the worker so transient heartbeat failures do not immediately cascade into job termination when checkpoint reporting remains healthy. The worker will continue job execution through temporary control-plane outages, and only trigger shutdown after a bounded grace policy is exceeded.

### Implementation Changes
- Add a heartbeat degradation state machine in worker runtime:
  - Enter degraded mode on consecutive heartbeat send failures.
  - Track `degraded_since`, `last_heartbeat_success_at`, and `last_checkpoint_report_success_at`.
  - Exit degraded mode immediately when heartbeat succeeds again.
- Add configurable grace policy (adaptive):
  - New settings using multiplier + floor:
    - `RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER`
    - `RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS`
  - Effective grace window: `max(multiplier * heartbeat_interval_seconds, floor_seconds)`.
- Add checkpoint-health gating during degraded mode:
  - Define “checkpoint healthy” as last successful checkpoint *report* within `3x checkpoint_poll_interval_seconds`.
  - While within grace and checkpoint is healthy, keep job running and keep retrying heartbeat as normal.
- Add bounded shutdown decision:
  - If heartbeat remains failed beyond grace window and checkpoint is no longer healthy, trigger existing graceful cleanup path (`SIGTERM`, final checkpoint attempt, existing termination behavior).
  - Preserve current behavior for non-transient fatal errors (e.g., explicit job/process failure paths).
- Improve observability:
  - Add structured logs/events for:
    - `heartbeat_degraded_mode_entered`
    - `heartbeat_degraded_mode_recovered`
    - `heartbeat_degraded_mode_grace_extended_by_checkpoint_health`
    - `heartbeat_degraded_mode_shutdown_triggered`
  - Include elapsed outage duration, grace limit, and last checkpoint report age in log fields.

### Public Interfaces / Config Additions
- Worker runtime config additions (env aliases + defaults in worker settings):
  - `RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_MULTIPLIER` (default chosen below)
  - `RELAYMD_WORKER_HEARTBEAT_FAILURE_GRACE_FLOOR_SECONDS` (default chosen below)
- No orchestrator API contract changes.

### Test Plan
- Unit tests for degraded-mode policy:
  - Heartbeat fails transiently, checkpoint reports remain fresh -> worker does not terminate.
  - Heartbeat recovers before grace expiry -> degraded mode clears, no shutdown.
  - Heartbeat fails past grace and checkpoint freshness expires -> graceful termination path invoked.
- Timing-policy tests:
  - Verify `max(multiplier * heartbeat_interval, floor)` calculation.
  - Verify checkpoint freshness threshold of `3x checkpoint_poll_interval`.
- Regression tests:
  - Existing cleanup behavior still occurs when shutdown is triggered.
  - Existing success path unchanged when heartbeats are healthy.
- Logging assertions:
  - Degraded-mode lifecycle events emitted with expected fields.

### Assumptions and Defaults
- Default grace config:
  - `heartbeat_failure_grace_multiplier = 15`
  - `heartbeat_failure_grace_floor_seconds = 900`
  - With default 60s heartbeat interval, this yields a 15-minute grace.
- “Checkpoint healthy” is based on successful checkpoint **report RPC** recency (not local file writes).
- Post-grace action remains graceful termination (not indefinite run, not immediate hard fail).

---

### Cluster-Affinity Submit + Queue Blocking Visibility Plan

### Summary
Add per-job cluster affinity to `relaymd submit`, allowing one job to target one or more named SLURM cluster configs (for example `anvil-gpu`, `gilbreth-a30`) with strict no-fallback behavior. Add optional job comments captured at submit time and shown in frontend job details. Preserve lifecycle status semantics (`queued` stays `queued`) and expose explicit queue blocking reasons when affinity cannot currently run.

### Agreed Product Decisions
- Affinity policy:
  - No fallback to non-pinned clusters.
  - Affinity accepts exact cluster `name` values only.
  - Multiple clusters allowed via repeatable `--cluster`.
  - Duplicate `--cluster` values are deduplicated preserving first-seen order.
- Validation:
  - CLI validates names using existing settings resolution precedence.
  - Orchestrator re-validates as source of truth.
  - Fail fast in CLI (before bundle archive/upload) if provided names are unknown.
- Comment support:
  - New optional `--comment`.
  - Trimmed string with max length `2000`.
  - Whitespace-only normalizes to `null`.
  - Immutable after submit for now.
- Queue blocking semantics:
  - Persist job lifecycle status as `queued`; do not add a new lifecycle enum for blocked.
  - Add machine-readable reason field: `queue_blocked_reason`.
  - Initial codes:
    - `no_enabled_pinned_clusters`
    - `no_matching_pinned_clusters`
  - Frontend maps codes to operator-friendly labels.
- Requeue:
  - Requeue clone copies affinity and comment.
- Frontend display:
  - Jobs list keeps primary status `queued`; show blocked indicator as secondary text/badge.
  - Add `Blocked` overview metric tile.
  - Selected job detail panel shows `Pinned Clusters` and `Comment`.

### Backend / Data Model Changes
- `packages/relaymd-core` (`Job`, `JobCreate`, `JobRead`):
  - Add nullable persisted fields:
    - `preferred_clusters_json: str | None`
    - `comment: str | None`
    - `queue_blocked_reason: str | None`
  - Expose parsed `preferred_clusters: list[str]` in `JobRead`.
  - Keep backward compatibility for existing rows (`null` defaults).
- Orchestrator jobs router (`src/relaymd/orchestrator/routers/jobs_operator.py`):
  - Accept `preferred_clusters` and `comment` in create payload.
  - Validate against configured cluster names.
  - Normalize/trim/dedupe affinity list and comment.
  - Populate persisted fields and return in `JobRead`.
- Scheduler/provisioning paths:
  - Filter job eligibility and cluster submission decisions using job affinity.
  - Compute and persist `queue_blocked_reason` for queued jobs when affinity is unschedulable due to:
    - all pinned clusters disabled
    - pinned clusters no longer present in runtime config
  - Clear `queue_blocked_reason` when job becomes schedulable or transitions out of queued.
- Requeue path:
  - Copy `preferred_clusters_json`, `comment`, and reset `queue_blocked_reason` based on current eligibility.

### CLI Changes (`relaymd submit`)
- Add repeatable option:
  - `--cluster <name>` (multiple allowed).
- Add optional:
  - `--comment <text>`.
- Submit flow updates:
  - Resolve known cluster names from loaded settings.
  - Validate/dedupe clusters before archive/upload.
  - Normalize comment (`trim`, length check, empty -> `null`).
  - Send new fields in `JobCreate`.
- JSON output updates:
  - Include `preferred_clusters`, `comment`, and `queue_blocked_reason` in `--json` output.

### Frontend Changes
- Types/API:
  - Extend `JobRead` type with `preferred_clusters`, `comment`, `queue_blocked_reason`.
- Jobs view:
  - Show secondary blocked indicator when `status=queued` + `queue_blocked_reason` set.
  - Add readable mapping for blocking reason codes.
  - In selected job details, render:
    - `Pinned Clusters` (comma-separated or `-`)
    - `Comment` (preserve line breaks; show `-` when null)
- Metrics:
  - Add `Blocked` tile counting queued jobs with non-null `queue_blocked_reason`.

### Migration / Compatibility
- Add DB migration for new nullable columns on `job` table:
  - `preferred_clusters_json`
  - `comment`
  - `queue_blocked_reason`
- Backfill existing rows as `NULL`.
- Keep existing status enum unchanged to avoid transition/contract breakage.

### Test Plan
- CLI tests:
  - Accept multiple `--cluster`; dedupe duplicates.
  - Unknown clusters fail fast pre-upload with useful error.
  - `--comment` trim, max length enforcement, whitespace normalization.
- Orchestrator API tests:
  - Create job with valid affinity/comment persists and round-trips via `JobRead`.
  - Invalid affinity names rejected by API.
  - Create job with no affinity remains current behavior.
- Scheduling/provisioning tests:
  - Jobs only considered by pinned clusters.
  - `queue_blocked_reason=no_enabled_pinned_clusters` when all pinned disabled.
  - `queue_blocked_reason=no_matching_pinned_clusters` when config drift removes pinned names.
  - Reason clears when constraints become satisfiable.
- Requeue tests:
  - Requeued job copies affinity/comment and has correct initial blocking reason.
- Frontend tests:
  - Blocked indicator rendering and code-to-label mapping.
  - Details panel shows pinned clusters/comment.
  - `Blocked` metric count updates correctly.
