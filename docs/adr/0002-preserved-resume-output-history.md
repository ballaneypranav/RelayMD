# ADR 0002: Preserved Resume Output History

## Status
Accepted

## Date
2026-05-15

## Context
Some MD payloads resume correctly from checkpoints but overwrite operator-useful files such as top-level engine logs on each resumed execution. RelayMD already distinguishes live resumable state from resume-preserved output in its glossary, but the current checkpoint manifest and worker flow only model the latest live copy. That loses prior log generations across handoffs even when the current resumable file is restored correctly.

## Decision
RelayMD will add an explicit bundle config field, `resume_preserved_output_paths`, for files whose current copy must remain part of normal checkpoint state while prior pre-resume generations are preserved as history. Paths declared there are included in ordinary checkpointing automatically and must not also appear in `checkpoint_watch_paths`.

RelayMD will extend the checkpoint manifest with a separate `preserved_outputs` section grouped by original relative path. On resume, the worker will load the remote checkpoint manifest, preserve the prior remote copy of each configured resume-preserved file into `jobs/<job_id>/checkpoints/preserved-output/...`, then hydrate only the latest live copy from `files` into the bundle root. Historical preserved copies are never hydrated to workers.

Checkpoint download keeps existing paths intact: current resumable files continue to download under `files/`, and preserved history is added under `preserved-output/`. Preserved-output capture is fail-fast during resume preparation. The first version keeps all preserved snapshots and does not prune them automatically.

## Consequences
### Positive
- Preserves overwritten log generations across worker handoffs without changing live resume semantics.
- Keeps worker resume cost bounded by hydrating only the latest live checkpoint files.
- Makes operator checkpoint downloads lossless for both current state and preserved history.

### Trade-offs
- Checkpoint manifest schema becomes more complex.
- Resume preparation performs extra storage work before hydration/launch.
- Bundle validation must enforce new overlap and path rules.

### Non-goals
- No worker-side hydration of preserved history.
- No continuous per-write versioning during a single resume segment.
- No automatic retention pruning in the initial implementation.

## Alternatives Considered
1. Best-effort preserved-output capture while still allowing resume to continue.
   - Rejected: makes history preservation advisory instead of contractual.
2. Mix preserved history into the normal `files` manifest section.
   - Rejected: blurs live resumable state with operator-facing history and risks accidental worker hydration.
3. Require the same path in both `checkpoint_watch_paths` and `resume_preserved_output_paths`.
   - Rejected: duplicates configuration and creates drift risk for one conceptual behavior.
4. Hydrate preserved history to workers on resume.
   - Rejected: adds download/hash cost without helping the payload resume correctly.

## Rollout Notes
- Extend worker bundle config parsing and validation for `resume_preserved_output_paths`.
- Extend manifest upload/download code to persist and consume `preserved_outputs`.
- Keep CLI checkpoint download backward-compatible by preserving the existing `files/` layout and adding `preserved-output/` as an additive tree.
