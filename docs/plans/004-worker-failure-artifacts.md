# Plan 004: Worker Failure Artifacts and Checkpoint Rollback Protection

## Goal
Protect the last accepted resumable checkpoint from failed or regressed worker segments while preserving enough diagnostics for operators to investigate failures.

## Scope
- Add worker failure artifacts stored outside checkpoint state.
- Stop worker-detected failure paths from uploading or reporting final checkpoints.
- Add `failure_artifact_paths` to bundle config for diagnostic files captured on any worker-detected failure.
- Include `progress_file_path` in checkpoint state automatically so resumed workers can derive a progress baseline from hydrated state when available.
- Detect excessive progress rollback on resumed jobs before checkpoint sync overwrites object storage.
- Expose the latest failure artifact path through the orchestrator API and job history.
- Do not add an orchestrator-side progress regression guard in the first implementation.
- Do not include checkpoint files in failure artifacts.

## Locked Decisions
1. Worker-detected failures produce failure artifacts, not new checkpoint state.
2. Failure artifacts live outside `jobs/{job_id}/checkpoints/`, under `jobs/{job_id}/failures/{failure_id}/`.
3. Failure artifacts contain diagnostics and logs only. They must not contain checkpoint files.
4. Failure artifacts are never hydrated into a future resume segment.
5. Failure artifact upload is best-effort and must not block `fail_job`.
6. `failure_artifact_paths` is a new bundle config field for diagnostic files to capture on any worker-detected failure.
7. `fatal_log_path` remains a supervision rule. If present, it may also be included in failure artifacts.
8. `progress_file_path` is implicitly part of resumable checkpoint state; users do not need to repeat it in `checkpoint_watch_paths`.
9. Excessive progress rollback uses an absolute tolerance of `0.05`.
10. Excessive progress rollback fails the job; it is not cancellation.
11. Regression control applies only to resumed jobs with a hydrated progress baseline.
12. If no progress file is hydrated on resume, do not enforce regression control for that segment.
13. Planned handoff and explicit operator cancellation remain resumable control-flow paths and may preserve checkpoint state.
14. If a planned handoff observes excessive progress rollback, fail the job and upload a failure artifact instead of completing handoff.
15. Do not add an orchestrator-side rollback guard; the worker must decide before checkpoint files are uploaded.
16. The orchestrator stores and exposes the latest failure artifact path so operators can discover diagnostics.

## Bundle Config Changes
Extend worker bundle config parsing and validation:

- `failure_artifact_paths: list[str] | str | None`
  - Optional.
  - Uses the same relative-path safety rules as checkpoint watch paths.
  - Supports exact relative paths and glob patterns, matching `checkpoint_watch_paths` behavior.
  - Captured only into failure artifacts, not checkpoint state.

Implicit path behavior:

- Add `progress_file_path` to the effective checkpoint watch set.
- Do not require users to list `progress_file_path` in `checkpoint_watch_paths`.
- Decide whether to reject or silently deduplicate explicit overlap with `checkpoint_watch_paths`.
  - Recommended: silently deduplicate because `progress_file_path` was already mandatory and this is an additive safety behavior.

Keep separate meanings:

- `fatal_log_path`: file scanned for configured fatal patterns.
- `failure_artifact_paths`: files copied into diagnostic artifacts when any worker-detected failure occurs.

## Failure Artifact Contract
Remote layout:

- `jobs/{job_id}/failures/{failure_id}/manifest.json`
- `jobs/{job_id}/failures/{failure_id}/diagnostics.json`
- `jobs/{job_id}/failures/{failure_id}/files/<relative_path>`

`failure_id` should be stable enough for humans and unique enough for retries:

- Recommended shape: UTC timestamp plus worker ID suffix, e.g. `20260516T203015Z-{worker_id}`.

Minimum `manifest.json` fields:

- `schema_version`
- `job_id`
- `worker_id`
- `provider_id`
- `created_at`
- `reason`
- `detail`
- `failure_artifact_path`
- `files`
- `upload_failures`

Minimum copied file metadata:

- `relative_path`
- `remote_key`
- `size_bytes`
- `sha256`
- `captured_at`

Minimum `diagnostics.json` fields:

- `job_id`
- `worker_id`
- `provider_id`
- `reason`
- `detail`
- `progress`
- `progress_codes`
- `resume_progress_baseline`
- `progress_regression_tolerance`
- `checkpoint_manifest_path`
- `latest_checkpoint_manifest_path`
- `failure_artifact_paths`
- `fatal_log_path`
- `created_at`

If artifact upload partially fails:

- Upload whatever can be uploaded.
- Include failures in `upload_failures` when the manifest can still be uploaded.
- Log upload failures.
- Continue to `fail_job`.

## API and Model Changes
Shared models:

- Add `latest_failure_artifact_path: str | None` to `Job`, `JobRead`, and generated client models.
- Add a worker failure-report payload or extend the existing fail endpoint to accept:
  - `failure_artifact_path: str | None`
  - `reason: str | None`
  - `message/detail: str | None`

Recommended API shape:

- Extend `POST /jobs/{job_id}/fail` with an optional typed body.
- Keep body optional for backward compatibility with existing workers/tests.

Orchestrator behavior:

- On `fail_job`, store `latest_failure_artifact_path` when provided.
- Include artifact path and reason/detail in the `failed` history event payload.
- Expose `latest_failure_artifact_path` in operator job list/get responses.
- Include `latest_failure_artifact_path` in CLI list/export data once the generated client is refreshed.

Generated client:

- Run `./scripts/generate_api_client.sh` after OpenAPI changes.
- Do not hand-edit generated client files.

## Worker Behavior
Resume preparation:

1. Download and parse the checkpoint manifest when `latest_checkpoint_manifest_path` is present.
2. Capture resume-preserved outputs as today.
3. Hydrate checkpoint files into the bundle root.
4. Read `progress_file_path` from the hydrated bundle root.
5. If the hydrated progress file is present and valid, store it as `resume_progress_baseline` in memory for the whole segment.
6. If the hydrated progress file is missing or invalid, set no baseline and do not enforce rollback control for that segment.

Progress regression check:

- Run before every checkpoint manifest cycle, including:
  - regular checkpoint polling
  - shutdown/SIGTERM checkpoint sync if it is a failure path
  - planned handoff final sync
  - operator cancellation sync, if the policy later treats it as eligible for rollback detection
- First-cut minimum: enforce before regular checkpoint polling and handoff final sync.
- If `latest_progress < resume_progress_baseline - 0.05`:
  - Terminate the payload if still running.
  - Upload a failure artifact with reason `excessive_progress_rollback`.
  - Call `fail_job` with the failure artifact path.
  - Do not call `_sync_checkpoint_manifest_cycle`.
  - Do not call `report_checkpoint`.
  - Do not call `complete_handoff`.

Worker-detected failure paths that should upload failure artifacts and avoid checkpoint writes:

- Payload exits nonzero.
- Supervision failure:
  - `startup_progress_timeout`
  - `progress_timeout`
  - `max_runtime_exceeded`
  - `fatal_log_match`
- OpenMM/platform preflight failure.
- Checkpoint hydration failure.
- Excessive progress rollback.
- Bundle config failure after assignment, if enough context exists to upload an artifact.
- Any other worker path that reports `fail_job`.

Control-flow paths that may preserve checkpoint state:

- Planned handoff, unless excessive progress rollback is detected.
- Explicit operator cancellation.
- Worker shutdown fallback that is intended to preserve resumable state rather than classify payload failure.

Refactor target:

- Introduce a single helper for worker failure finalization, e.g. `_fail_assigned_job(...)`, that:
  - uploads a failure artifact best-effort
  - calls `gateway.fail_job(...)` with artifact metadata
  - returns a clear control-flow result
- Route all worker-detected failure paths through this helper.

## Checkpoint Sync Changes
- Include `progress_file_path` in the effective checkpoint watch paths.
- Ensure checkpoint sync still deduplicates watched files by relative path.
- Do not run checkpoint sync after worker-detected failures.
- Keep existing non-destructive missing-file behavior from planned handoff work.
- Preserve existing checkpoint sync behavior for completion, handoff, cancellation, and non-failure shutdown paths unless rollback control fails first.

## CLI and Frontend Behavior
- Add `latest_failure_artifact_path` to job list/detail/export surfaces where checkpoint fields already appear.
- If frontend has a job detail panel, show a link or copyable storage key for the latest failure artifact.
- Do not add failure artifact download commands in the first cut unless implementation is already cheap.
- Existing checkpoint download commands must ignore failure artifacts.

## Documentation Changes
Update after implementation:

- `docs/adr/0004-worker-failure-artifacts.md` if implementation details diverge from this plan.
- `docs/worker-internals.md`
  - failure artifact behavior
  - `failure_artifact_paths`
  - progress rollback enforcement
  - failure paths no longer uploading final checkpoints
- `docs/job-lifecycle.md`
  - failure path does not advance resumable checkpoint state
  - handoff/cancellation remain resumable control flow
- `docs/storage-layout.md`
  - add `jobs/{job_id}/failures/{failure_id}/`
  - clarify that `checkpoints/` is resumable state only
- `docs/cli.md`
  - bundle config example includes `failure_artifact_paths`
  - update old language that says failure uploads final checkpoints
- `docs/architecture.md`
  - reinforce checkpoint state vs diagnostic artifact separation if useful.

## Implementation Sequence
1. Extend core `Job`/`JobRead` models with `latest_failure_artifact_path`.
2. Add migration/backfill handling for the new nullable job field.
3. Extend worker fail endpoint model and route to accept optional failure artifact metadata.
4. Persist failure artifact metadata and add it to failed history events.
5. Regenerate the API client with `./scripts/generate_api_client.sh`.
6. Extend worker gateway `fail_job` to accept optional artifact path/reason/detail while preserving old call sites.
7. Extend `BundleExecutionConfig` with `failure_artifact_paths` parsing and validation.
8. Add helper to compute effective checkpoint watch paths including `progress_file_path`.
9. Implement failure artifact manifest/diagnostics/file upload helpers.
10. Implement hydrated progress baseline capture after checkpoint hydration.
11. Add progress rollback check before checkpoint sync and handoff completion.
12. Refactor worker-detected failure paths through the failure finalization helper.
13. Update CLI/frontend surfaces for `latest_failure_artifact_path`.
14. Update docs.
15. Run `graphify update .`.

## Validation Plan
Backend tests:

- `fail_job` without body remains accepted for backward compatibility.
- `fail_job` with `failure_artifact_path` stores `latest_failure_artifact_path`.
- Failed history event includes failure artifact metadata when provided.
- Job read/list responses expose `latest_failure_artifact_path`.
- Requeue clone behavior either preserves or clears `latest_failure_artifact_path` according to chosen operator semantics.
  - Recommended: preserve it as historical context on the failed source job; cloned job starts with no failure artifact.

Worker config tests:

- `failure_artifact_paths` accepts string and list values.
- Invalid absolute or parent-traversal failure artifact paths fail config validation.
- `progress_file_path` is included in checkpoint watch paths without duplicate uploads.

Worker failure artifact tests:

- Payload nonzero exit uploads failure artifact and calls `fail_job`; it does not upload checkpoint manifest or report checkpoint.
- Fatal log match captures `fatal_log_path` and configured `failure_artifact_paths` into a failure artifact.
- Artifact upload failure is logged but does not prevent `fail_job`.
- Missing configured diagnostic files are recorded in artifact upload failures without failing the whole artifact.

Worker rollback tests:

- Resumed job with hydrated progress baseline `0.50` and current progress `0.46` does not fail.
- Resumed job with hydrated progress baseline `0.50` and current progress `0.44` uploads failure artifact, calls `fail_job`, and does not upload checkpoint files or manifest.
- Resumed job with no hydrated progress file does not enforce rollback control.
- Planned handoff with excessive progress rollback fails instead of calling `complete_handoff`.
- First-run job does not enforce rollback control.

Regression tests for preserved behavior:

- Successful completion still uploads and reports final checkpoint.
- Planned handoff without rollback still uploads final checkpoint when available and completes handoff.
- Explicit operator cancellation still preserves checkpoint behavior.
- Existing checkpoint manifest hydration and resume-preserved-output tests still pass.

CLI/frontend tests:

- Job list/detail/export tolerate and display `latest_failure_artifact_path`.
- Generated API client models include the new field.

## Rollout Notes
- This changes API models and requires generated client refresh.
- This changes source, tests, docs, and operator-visible behavior, so the PR must include the repository-required version bump before push.
- Existing workers remain compatible if the fail endpoint keeps its request body optional.
- The behavior intentionally changes old docs/tests that expected final checkpoint upload on failure; update those tests rather than preserving the old behavior.
