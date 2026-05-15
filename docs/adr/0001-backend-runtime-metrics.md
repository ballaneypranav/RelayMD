# ADR 0001: Backend-Owned Runtime Metrics for Jobs

## Status
Accepted

## Date
2026-05-15

## Context
RelayMD currently computes runtime-related values in multiple places:
- Backend provides job status/timestamps and history events.
- Frontend computes total runtime using history segments when available.
- CLI export computes runtime from current timestamps only.

This created inconsistent operator outputs (for example, runtime shown in frontend vs CLI export for the same running job).

## Decision
RelayMD will centralize runtime metric computation in the backend and expose raw-second metrics on job read/list payloads:
- `runtime_seconds` (non-null numeric)
- `etc_seconds` (nullable numeric)
- `ett_seconds` (nullable numeric)

Definitions:
- Runtime scope is a single job ID.
- `runtime_seconds` is total runtime across all segments for that job ID.
- `etc_seconds` is estimated remaining runtime.
- `ett_seconds` is estimated total runtime (`runtime_seconds + etc_seconds`).

The backend is the only component that computes these metrics. Frontend and CLI render or export backend values and do not maintain duplicate runtime logic.

## Consequences
### Positive
- Consistent runtime values across API, frontend, and CLI.
- Reduced duplicated logic in clients.
- Easier testing and auditing of runtime semantics.

### Trade-offs
- Backend list/read serialization does more computation.
- API contract changes require client/test updates.

### Non-goals
- No chain-level runtime aggregation across requeued job IDs.
- No formatted-duration strings as API source-of-truth fields.

## Alternatives Considered
1. Keep runtime logic in frontend and patch CLI to match.
   - Rejected: still duplicates domain logic and risks future drift.
2. Persist precomputed runtime columns in DB and update on each event.
   - Deferred: potentially useful for scale, but unnecessary for initial consistency fix.
3. Compute only in `/jobs/{id}/history` and have clients derive list values.
   - Rejected: keeps client-side coupling to history polling and transformation logic.

## Rollout Notes
- Replace legacy client-facing runtime fields/columns that implied formatted values.
- Move list views to `/jobs` runtime metrics.
- Keep `/jobs/{id}/history` for timeline details and diagnostics.
