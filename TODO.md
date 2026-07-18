# TODO

- Frontend: surface worker checkpoint-cycle errors in operator UI status/details, including:
  - `watch_file_cap_exceeded`
  - `potential_write_in_progress`
  - `file_disappeared`
  - `manifest_upload_failed`

2026/05/12
Remove latest_checkpoint_path from code once all running workers complete

2026/05/17
Infisical 429 handling for CLI settings hydration

- Document current Infisical Cloud rate limits in docs:
  - Read: 200/min (Free), 350/min (Pro)
  - Write: 90/min (Free), 200/min (Pro)
  - Secret: 120/min (Free), 300/min (Pro)
  - Identity creation: 30/min
  - Project creation: 30/min
- Add 429-aware retry logic in `packages/relaymd-core/src/relaymd/core_secret_management.py`:
  - Detect rate-limit responses and respect `Retry-After` when present.
  - Fallback to parsing "try again in N seconds" from Infisical error messages.
  - Add bounded exponential backoff with jitter for non-429 transient failures.
- Reduce Infisical request burst during settings hydration:
  - Prefer one bulk/list secret fetch per path+environment over N `getSecret` calls.
  - If bulk endpoint is not available in current SDK path, add lightweight in-process caching per run.
- Add tests:
  - Retries on 429 with server-directed wait.
  - No retry for invalid credentials errors.
  - Secret hydration remains deterministic under retries.

2026/05/17
Resume-as-new job flow for changed input bundles

- Add a supported operator flow to submit a new immutable bundle while resuming
  from an existing job's latest checkpoint.
- Prefer CLI shape such as `relaymd submit <dir> --resume-from-job <job-id>` or
  `relaymd jobs resume-as-new <job-id> <dir>`.
- Preserve `latest_checkpoint_manifest_path` and `last_checkpoint_at` from the
  source job, but use the new job ID's `input_bundle_path`.
- Record job history linking old job ID, new job ID, checkpoint source, and new
  bundle path.
- Keep workload-specific parameters such as AToM `workers-per-gpu` in generated
  input bundles, not as RelayMD `--set` runtime parameters.
