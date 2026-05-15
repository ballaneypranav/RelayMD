# Plan 001: Backend Runtime Metrics Migration

## Goal
Move runtime/ETA calculation to the backend so frontend and CLI only consume backend-provided raw-second fields.

## Scope
- No code changes in this planning task.
- Document implementation plan only.
- Runtime scope is a single job ID (not requeue chain aggregate).

## Locked Decisions
1. Backend is the single source of truth for runtime math.
2. Add raw-second fields to `JobRead`:
   - `runtime_seconds` (always numeric)
   - `etc_seconds` (nullable)
   - `ett_seconds` (nullable)
3. `runtime_seconds` means total runtime across all worker segments for that job ID.
4. `etc_seconds` is estimated remaining runtime.
5. `ett_seconds` is estimated total runtime (`runtime_seconds + etc_seconds`).
6. Progress is clamped to `[0, 1]` before ETA math.
7. ETA is undefined for non-active statuses or invalid progress (`<=0` or `>=1`): return `null` for `etc_seconds` and `ett_seconds`.
8. For active segments, runtime anchors at `running` when present (not `assigned`).
9. Frontend keeps polling `/jobs` for list metrics; `/jobs/{job_id}/history` is for detail views only.
10. Remove `total_runtime` from frontend/CLI usage.
11. CSV output should use raw numeric timing fields only.

## Backend Behavior
- Compute `runtime_seconds` from persisted events-derived segments when available.
- If events are missing, use derived fallback events from job timestamps.
- `runtime_seconds` remains numeric even in fallback cases.
- `etc_seconds` and `ett_seconds` are computed from `runtime_seconds` and `progress` only.

## API Contract Changes
- Extend `JobRead` with:
  - `runtime_seconds: float`
  - `etc_seconds: float | null`
  - `ett_seconds: float | null`
- Keep `JobHistoryRead` focused on events/segments/totals (no new runtime summary fields required).

## Frontend Changes (Planned)
- Use backend `runtime_seconds`, `etc_seconds`, `ett_seconds` for table columns.
- Stop using history-derived runtime for table rows.
- Continue fetching history on row expansion/selection for timeline details.
- Render `null` timing fields as `-`.

## CLI Changes (Planned)
- `jobs export-csv` to output raw timing columns:
  - `runtime_seconds`
  - `etc_seconds`
  - `ett_seconds`
- Remove formatted timing export columns currently used for runtime/total_runtime/etc.
- Keep non-timing descriptive columns as-is.

## Documentation Changes (Planned)
- Add/refresh glossary in `CONTEXT.md` with canonical timing terms.
- Add ADR documenting the decision to centralize runtime metrics in backend and expose raw-second fields.

## Implementation Sequence
1. Backend model + serializer + tests.
2. Frontend consume new fields for list metrics; keep history for details only.
3. CLI export schema and tests updated for raw timing fields.
4. Documentation updates (`CONTEXT.md`, ADR).
5. Regenerate API client (`./scripts/generate_api_client.sh`) and update impacted tests/artifacts.

## Validation Plan
- Targeted backend unit/integration tests for runtime/ETC/ETT semantics.
- Frontend tests for column rendering using backend raw fields.
- CLI tests for CSV schema/values and null handling.
- Final verification that job rows with multiple segments show consistent runtime across API, frontend, and CLI.
