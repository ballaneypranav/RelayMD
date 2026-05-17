# ADR 0004: Worker Failures Produce Diagnostic Artifacts, Not Checkpoints

RelayMD will keep worker-detected failure output separate from resumable checkpoint state. When a worker fails a job because of payload exit, supervision failure, excessive progress rollback, hydration/preflight failure, or another worker-detected failure condition, it will best-effort upload a failure artifact under `jobs/{job_id}/failures/{failure_id}/` and then report the job as `failed`; it will not overwrite checkpoint files, upload a new checkpoint manifest, or report a new checkpoint observation for that failed segment. This protects the last accepted resumable checkpoint from being replaced by state produced during a failed or regressed execution while still preserving diagnostics for operators.

## Status
Accepted

## Consequences
- Failure artifacts contain diagnostics and logs only; they do not contain checkpoint files and are never hydrated into future resume segments.
- The worker bundle will support `failure_artifact_paths` for diagnostic files to capture on any worker-detected failure. Existing `fatal_log_path` remains a supervision rule and may be included in failure artifacts when present.
- Failure artifact upload is best-effort. A failed artifact upload must not prevent the worker from reporting `failed`.
- Explicit operator cancellation and planned handoff remain resumable control-flow paths and may continue preserving checkpoint state unless the worker detects excessive progress rollback.
- `progress_file_path` is implicitly part of resumable checkpoint state so resumed workers can derive a resume progress baseline from hydrated state when available.
- Excessive progress rollback is enforced only for resumed jobs with a hydrated progress baseline. If no progress baseline is hydrated, the worker does not enforce rollback control for that segment.
- The orchestrator records and exposes the latest failure artifact path so operators can discover failure diagnostics.

## Considered Options
1. Upload final checkpoints on failure, as the worker did previously.
   - Rejected because a failed segment may have produced corrupt, incomplete, or regressed state that should not replace the last accepted resumable checkpoint.
2. Put failure diagnostics under `jobs/{job_id}/checkpoints/`.
   - Rejected because colocating diagnostics with resumable checkpoint state makes it easier for future code or operators to confuse failure output with restartable state.
3. Enforce progress rollback in the orchestrator.
   - Rejected because the worker must decide before uploading checkpoint files; an orchestrator-only guard would detect the rollback too late to protect object storage.
