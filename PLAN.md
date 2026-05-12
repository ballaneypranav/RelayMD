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
