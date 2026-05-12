# Checkpoint Hydration Before Worker Start

## Summary
Implement worker-side checkpoint hydration so a resumed job starts from the extracted input bundle plus restored checkpoint files. The worker will load the persisted checkpoint manifest, download each tracked checkpoint file into its manifest-relative location under the extracted bundle root, and only then start the job command.

## Key Changes
- Add a worker helper in `packages/relaymd-worker/src/relaymd/worker/main.py` that hydrates checkpoint files from the manifest:
  - Read `manifest["files"]` entries.
  - For each entry, require a string `remote_key`.
  - Treat the manifest key as the source of truth and download each file to `bundle_root / relative_path`.
  - Create parent directories as needed.
  - Validate destination paths are manifest-relative, not absolute, contain no `..`, and resolve inside `bundle_root`.
  - Reject destinations that would traverse through or overwrite unsafe symlinks.
- Change `_run_assigned_job` startup order:
  - Download and extract the input bundle first.
  - Load the persisted manifest with `_load_persisted_manifest`.
  - If `assignment.latest_checkpoint_path` is present, hydrate checkpoint files into the extracted bundle before constructing/starting `JobExecution`.
  - Remove the current unused direct download of `assignment.latest_checkpoint_path` to a temp file.
- Failure behavior:
  - If hydration is required and any manifest file cannot be validated or downloaded, log a structured `checkpoint_hydration_failed` event, call `context.gateway.fail_job(...)`, and return before `execution.start()`.
  - Do not silently start from scratch after a failed hydration attempt.
- Logging:
  - Log `checkpoint_hydration_started`, `checkpoint_file_hydrated`, and `checkpoint_hydration_completed`.
  - Include `job_id`, `relative_path`, and `remote_key` where relevant.
  - Keep logs structured, no f-string log messages.
- Version/repo hygiene:
  - Work on a non-`main` branch before editing.
  - Include the required RelayMD version bump for source/test changes per repo policy.
  - Run `graphify update .` after code changes.

## Test Plan
- Add/update focused worker tests in `packages/relaymd-worker/tests/test_main_loop.py`:
  - Resumed job hydrates checkpoint files into the extracted bundle before `JobExecution.start()`.
  - Existing input bundle files remain present; checkpoint files overlay only their manifest-relative paths.
  - Hydrated nested paths such as `r0/FOL_APT.out` create directories and land in the correct location.
  - Unsafe relative paths, absolute paths, and `..` paths fail hydration and prevent job start.
  - Missing or non-string `remote_key` fails hydration and prevents job start.
  - Storage download failure during hydration fails the job and prevents job start.
  - First checkpoint cycle after successful hydration does not prune hydrated manifest entries as deleted.
- Run targeted checks:
  - `uv run pytest packages/relaymd-worker/tests/test_main_loop.py`
  - `uv run ruff check packages/relaymd-worker/src/relaymd/worker/main.py packages/relaymd-worker/tests/test_main_loop.py`
  - `uv run pyright packages/relaymd-worker/src/relaymd/worker/main.py packages/relaymd-worker/tests/test_main_loop.py`

## Assumptions
- `latest_checkpoint_path` for current jobs points to the checkpoint manifest, not to a tarball-style checkpoint artifact.
- The checkpoint manifest’s `files` map is the canonical restore contract.
- Hydration should fail closed: a resume job with unusable checkpoint metadata must fail before launching rather than starting from scratch.
- No orchestrator API/schema change is needed for this fix.
