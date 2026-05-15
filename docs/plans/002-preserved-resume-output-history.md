# Plan 002: Preserved Resume Output History

## Goal
Preserve prior generations of resumable-but-overwriting output files across worker handoffs without changing how the latest live checkpoint copy is restored for resume.

## Scope
- Add resume-preserved output support in worker bundle config, checkpoint manifest handling, and resume preparation flow.
- Extend checkpoint download to include `preserved-output/` without changing existing live-file paths.
- Add validation and tests for config overlap, manifest shape, resume capture, and checkpoint download behavior.
- Do not add preserved-output pruning or a separate CLI inspection command in the first cut.

## Locked Decisions
1. Add an explicit bundle config field: `resume_preserved_output_paths`.
2. Files declared in `resume_preserved_output_paths` are included in ordinary checkpoint state automatically.
3. A path must not appear in both `checkpoint_watch_paths` and `resume_preserved_output_paths`; bundle validation fails fast.
4. The latest live copy of a resume-preserved file remains part of normal checkpoint `files` state and is hydrated on resume.
5. Prior generations are stored separately in manifest `preserved_outputs` and remote `checkpoints/preserved-output/...`.
6. Historical preserved copies are never hydrated to workers.
7. Preserved history is captured from checkpoint storage during resume preparation, not from the input bundle.
8. Preserved-output capture happens before live file hydration and before payload launch.
9. Preserved-output capture is fail-fast during resume preparation.
10. `preserved_outputs` is grouped by original relative path, not flattened.
11. Snapshots are ordered by RelayMD `resume segment`, not payload-specific directory names such as replica folders.
12. Resume-segment numbering starts at `1` for the first resumed handoff; the initial first run has no preserved snapshot.
13. Checkpoint download keeps existing `files/` behavior and adds `preserved-output/` as an additive tree.
14. The initial version retains all preserved snapshots and does not prune automatically.

## Backend and Worker Behavior
- Parse and validate `resume_preserved_output_paths` in bundle config using the same relative-path safety model as checkpoint watch paths.
- Internally merge `resume_preserved_output_paths` into the watched checkpoint set for ordinary checkpoint uploads.
- Reject bundle configs where any resolved path appears in both ordinary checkpoint watch config and resume-preserved config.
- During resume preparation:
  1. Download and parse the remote checkpoint manifest.
  2. For each configured resume-preserved path that exists in remote `files`, copy the remote current file into a new preserved-output object keyed by original relative path and resume segment.
  3. Update manifest `preserved_outputs` metadata.
  4. Hydrate live checkpoint `files` into the bundle root.
  5. Launch the payload.
- If a configured resume-preserved path has no remote `files` entry in the manifest yet, skip preserved capture for that path for that resume.

## Manifest Contract Changes
- Keep existing live checkpoint state under:
  - `files`
- Add a separate history section:
  - `preserved_outputs`
- Shape:
  - `preserved_outputs["<relative_path>"]["snapshots"] = [...]`
- Minimum snapshot metadata:
  - `resume_segment`
  - `remote_key`
  - `size_bytes`
  - `sha256`
  - `captured_at`

## Remote Object Layout
- Keep current live checkpoint files under:
  - `jobs/<job_id>/checkpoints/files/<relative_path>`
- Add preserved history under:
  - `jobs/<job_id>/checkpoints/preserved-output/<relative_path>/<resume-segment>/...`
- Preserve original relative path structure beneath `preserved-output/`.

## CLI Changes (Planned)
- Keep `relaymd jobs checkpoint download` live-file behavior unchanged:
  - `manifest.json` at output root
  - live checkpoint files under `files/`
- Add preserved history download under:
  - `preserved-output/`
- No new first-cut CLI inspection command for preserved history.

## Documentation Changes (Planned)
- Update `CONTEXT.md` with canonical terms:
  - `resume-preserved output`
  - `preserved output sidecar`
  - `resume segment`
- Add ADR documenting the config, manifest, storage, and hydration boundary decisions.
- Refresh worker/storage docs after implementation to explain preserved-output behavior and checkpoint download layout.

## Implementation Sequence
1. Extend bundle config schema and validation for `resume_preserved_output_paths`.
2. Refactor checkpoint watch resolution so resume-preserved paths participate in ordinary checkpoint uploads without duplicate declaration.
3. Extend worker manifest model/helpers for `preserved_outputs` and resume-segment bookkeeping.
4. Implement resume-time preserved-output capture from remote checkpoint storage before live hydration.
5. Extend CLI checkpoint download to materialize `preserved-output/` while keeping `files/` unchanged.
6. Update docs (`CONTEXT.md`, ADR, worker/storage/deployment docs as needed).

## Validation Plan
- Worker test: on resume, preserve remote pre-resume copy into `preserved_outputs` and still hydrate the live file from `files`.
- Worker/config validation test: overlapping path declaration across `checkpoint_watch_paths` and `resume_preserved_output_paths` fails fast.
- Worker test: configured resume-preserved path missing from remote `files` is skipped without failing ordinary first-run semantics.
- CLI checkpoint-download test: existing `files/` output remains unchanged and additive `preserved-output/` output is downloaded from the same manifest.
- Manifest tests: `preserved_outputs` grouping, resume-segment numbering, and required snapshot metadata are serialized correctly.
- Resume failure test: preserved-output capture failure aborts resume preparation before payload launch.
