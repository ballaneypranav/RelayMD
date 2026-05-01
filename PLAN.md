# RelayMD Job Contract And Machine Output Plan

## Summary

RelayMD is still in development and currently has only one real consumer:
`FR_ATM-LSFE-00-wibowo2013`. We can make breaking changes now to clean up the
job identity model, improve automation ergonomics, and move workload-specific
runtime requirements into the submitted job contract instead of global service
configuration.

Core goals:

- Make `relaymd submit` and other automation-facing commands emit stable JSON.
- Make the CLI-generated UUID the canonical job ID used everywhere.
- Add generic checkpoint download support so workflow projects do not need to
  locate B2 objects manually.
- Move `checkpoint_poll_interval_seconds` into the submitted bundle/job contract,
  with global config only as a default.
- Document the breaking changes clearly and update tests/docs around the new
  contract.

## Likely Files To Change

This is not exhaustive, but an implementation agent should inspect these first:

- `packages/relaymd-core/src/relaymd/models/job.py`
- `src/relaymd/orchestrator/routers/jobs.py`
- `src/relaymd/orchestrator/services/job_service.py`
- `src/relaymd/cli/commands/submit.py`
- `src/relaymd/cli/services/submit_service.py`
- `src/relaymd/cli/commands/jobs.py`
- `src/relaymd/cli/commands/workers.py`
- `src/relaymd/cli/commands/service.py`
- `src/relaymd/cli/commands/config.py`
- `src/relaymd/cli/commands/path.py`
- `src/relaymd/cli/services/jobs_service.py`
- `src/relaymd/cli/services/workers_service.py`
- `packages/relaymd-worker/src/relaymd/worker/main.py`
- `packages/relaymd-worker/src/relaymd/worker/config.py`
- `packages/relaymd-worker/src/relaymd/worker/job_execution.py`
- `packages/relaymd-api-client/openapi.json`
- `packages/relaymd-api-client/src/relaymd_api_client/`
- `tests/orchestrator/`
- `tests/cli/`
- `packages/relaymd-worker/tests/`
- `test/*/relaymd-worker.json`

After changing API models or routes, regenerate the API client:

```bash
./scripts/generate_api_client.sh
```

## Design Principles

- The job ID is the storage namespace. Input bundles and checkpoints for one job
  should live under the same `jobs/{job_id}/...` prefix.
- The bundle config is the workload contract. Project-specific execution behavior
  belongs with the submitted bundle, not in global RelayMD service config.
- Human CLI output and machine CLI output are separate interfaces. Automation
  should never parse Rich panels, tables, or prose.
- RelayMD remains domain-agnostic. It can download checkpoint artifacts, but
  domain-specific hydration/unpacking stays in the project lane.

## Breaking Changes

These changes intentionally break compatibility with any existing in-flight jobs
or old bundle contracts. This is acceptable because no jobs are currently running
and FR_ATM is the only consumer.

- `JobCreate` accepts a caller-provided `id`, and the CLI will provide it.
- New submissions use one canonical UUID for both DB identity and object-storage
  namespace.
- `relaymd submit` JSON output becomes the supported automation interface.
- `relaymd-worker.json` / `.toml` may include runtime contract fields such as
  `checkpoint_poll_interval_seconds`.
- The old assumption that worker checkpoint polling is purely global should be
  deprecated in docs and tests.

## Canonical Job ID

Current problem:

- `relaymd submit` generates a UUID for the input bundle path.
- The orchestrator generates a second UUID for the database job row.
- Checkpoints use the orchestrator UUID.
- This creates split storage paths:

```text
jobs/<cli-generated-id>/input/bundle.tar.gz
jobs/<orchestrator-job-id>/checkpoints/latest
```

Target behavior:

```text
jobs/<job-id>/input/bundle.tar.gz
jobs/<job-id>/checkpoints/latest
```

Implementation plan:

- Add `id: uuid.UUID | None = None` to `JobCreate`.
- In `relaymd submit`, generate `job_id` once before upload.
- Upload the input bundle to `jobs/{job_id}/input/bundle.tar.gz`.
- POST `JobCreate(id=job_id, title=title, input_bundle_path=b2_key)`.
- Have the orchestrator create the database row using the provided ID. If no ID
  is provided, the API may continue to generate one.
- Reject ID collisions with a clear typed error.
- Keep worker checkpoint path generation as-is, because workers already use
  `assignment.job_id` for `jobs/{job_id}/checkpoints/latest`.
- Update tests that currently assume the API owns ID generation.

Open API behavior:

- `POST /jobs` accepts an optional `id`.
- If `id` is omitted, the API may still generate one for manual/API callers.
- If `id` is present and already exists, return a typed conflict.
- Regenerate the OpenAPI schema and generated API client after changing
  `JobCreate`.

## Machine-Readable CLI Output

Add JSON output to commands likely to be called by scripts, workflow lanes, CI,
or monitoring tools.

Required commands:

- `relaymd submit --json`
- `relaymd status --json`
- `relaymd jobs list --json`
- `relaymd jobs show <id> --json`
- `relaymd workers list --json`
- `relaymd config show-paths --json`
- `relaymd path <name> --json`
- `relaymd jobs cancel <id> --json`
- `relaymd jobs requeue <id> --json`
- `relaymd jobs checkpoint download <job-id> --json`

Out of scope for this plan:

- `relaymd logs --json`, because raw log streaming is not naturally structured.
- `relaymd upgrade --json`, unless the implementation already has a clean
  release metadata object to return.

`relaymd submit --json` should emit at least:

```json
{
  "job_id": "00000000-0000-0000-0000-000000000000",
  "title": "07-production-relaymd:APT_FOL",
  "input_bundle_path": "jobs/00000000-0000-0000-0000-000000000000/input/bundle.tar.gz",
  "status": "queued"
}
```

`relaymd status --json` should emit service health only, at least:

```json
{
  "orchestrator": {
    "running": true,
    "healthy": true,
    "url": "http://localhost:36158"
  },
  "proxy": {
    "running": true,
    "healthy": true,
    "url": "http://localhost:36159"
  }
}
```

`relaymd jobs list --json` should emit an object with a `jobs` array:

```json
{
  "jobs": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "title": "07-production-relaymd:APT_FOL",
      "status": "queued",
      "input_bundle_path": "jobs/00000000-0000-0000-0000-000000000000/input/bundle.tar.gz",
      "latest_checkpoint_path": null,
      "created_at": "2026-05-01T00:00:00",
      "updated_at": "2026-05-01T00:00:00"
    }
  ]
}
```

`relaymd jobs show <id> --json` should emit one job object with the same fields
as entries in `job list`.

`relaymd jobs cancel <id> --json` and `relaymd jobs requeue <id> --json` should
emit the resulting job object after the transition.

`relaymd workers list --json` should emit an object with a `workers` array:

```json
{
  "workers": [
    {
      "id": "00000000-0000-0000-0000-000000000000",
      "status": "idle",
      "platform": "hpc",
      "gpu_model": "NVIDIA A30",
      "gpu_count": 1,
      "vram_gb": 24,
      "current_job_id": null,
      "last_heartbeat": "2026-05-01T00:00:00"
    }
  ]
}
```

`relaymd config show-paths --json` should emit absolute paths and active roots:

```json
{
  "service_root": "/depot/plow/apps/relaymd/current",
  "data_root": "/depot/plow/data/pballane/relaymd-service",
  "config_path": "/depot/plow/data/pballane/relaymd-service/config/relaymd-config.yaml",
  "env_path": "/depot/plow/data/pballane/relaymd-service/config/relaymd-service.env",
  "status_path": "/depot/plow/data/pballane/relaymd-service/state/relaymd-service.status",
  "logs_dir": "/depot/plow/data/pballane/relaymd-service/logs/service",
  "current_release": "/depot/plow/apps/relaymd/current"
}
```

`relaymd path <name> --json` should emit:

```json
{
  "name": "config",
  "path": "/depot/plow/data/pballane/relaymd-service/config"
}
```

JSON output rules:

- Write only JSON to stdout when `--json` is set.
- Send progress, warnings, and diagnostic text to stderr.
- Do not render Rich tables, panels, colors, or spinners in JSON mode.
- Keep field names stable and snake_case.
- Prefer structured error output for expected CLI failures where practical.
- Use nonzero exit codes for errors in both human and JSON modes.
- If structured JSON errors are implemented, use this shape:

```json
{
  "error": {
    "code": "no_checkpoint",
    "message": "Job has no checkpoint yet"
  }
}
```

## Checkpoint Download Command

Add a generic checkpoint download command so projects can retrieve the latest
RelayMD checkpoint without knowing B2 key conventions.

Required public command:

```bash
relaymd jobs checkpoint download <job-id> [--output PATH] [--json]
```

Do not add a singular `relaymd job checkpoint download` alias in this plan unless
the CLI already has an alias framework that makes it trivial. The public command
to document and test is the plural form above.

Behavior:

- Fetch job metadata from the orchestrator.
- Require `latest_checkpoint_path` to be present.
- Download that object through the configured storage client.
- If `--output` is a directory, write the checkpoint using the basename of the
  object key, or a stable default such as `<job-id>-checkpoint`.
- If `--output` is a file path, write exactly there.
- If `--output` is omitted, write to the current directory using a predictable
  name.
- Do not unpack or hydrate the archive. FR_ATM-specific hydration remains in the
  FR_ATM lane.
- Preserve the downloaded bytes exactly.
- Create parent directories for the output path if that matches existing CLI
  behavior; otherwise fail clearly when the parent is missing. Pick one behavior
  and test it.

Suggested JSON output:

```json
{
  "job_id": "00000000-0000-0000-0000-000000000000",
  "checkpoint_path": "jobs/00000000-0000-0000-0000-000000000000/checkpoints/latest",
  "local_path": "APT_FOL-relaymd-checkpoint.tar.gz",
  "bytes": 123456
}
```

Errors:

- Unknown job: clear not-found error.
- No checkpoint yet: clear nonzero exit with machine-readable error in JSON mode.
- Storage download failure: include object key and local target.
- Missing B2/Cloudflare storage configuration: reuse the existing CLI storage
  settings validation style where possible.

## Bundle Runtime Contract

Current minimal bundle config:

```json
{
  "command": ["bash", "run.sh"],
  "checkpoint_glob_pattern": "relaymd-checkpoint.tar.gz"
}
```

Target bundle config:

```json
{
  "command": ["bash", "run.sh"],
  "checkpoint_glob_pattern": "relaymd-checkpoint.tar.gz",
  "checkpoint_poll_interval_seconds": 60
}
```

Semantics:

- `checkpoint_poll_interval_seconds` controls how often the worker checks the
  job working directory for a newer checkpoint file.
- If present in the bundle config, it overrides the worker/global default for
  that job only.
- If absent, the worker falls back to `CHECKPOINT_POLL_INTERVAL_SECONDS`, then
  `worker_checkpoint_poll_interval_seconds`, then the built-in default.
- The value must be a positive integer. Consider allowing `0` only if tests and
  docs explicitly define it as continuous polling for local tests.
- For this plan, production validation should require `>= 1`. Unit tests may
  continue to construct runtime contexts with `0` directly where needed, but
  bundle config should reject `0`.

Why this belongs in the bundle:

- Different projects can write checkpoints at different cadences.
- FR_ATM currently writes `relaymd-checkpoint.tar.gz` every 600 seconds and wants
  RelayMD to poll every 60 seconds.
- Other projects may need slower polling, faster polling, or signal-only
  checkpoint behavior.
- The project lane should not need to mutate global RelayMD service config to
  express a workload-specific requirement.

Worker changes:

- Extend `BundleExecutionConfig` with `checkpoint_poll_interval_seconds`.
- Parse this field from JSON/TOML bundle config.
- Pass the effective interval into job execution logic for the assigned job.
- Keep `WorkerRuntimeSettings.checkpoint_poll_interval_seconds` as the fallback
  default.
- Log the effective interval at job start.

CLI changes:

- Add `relaymd submit --checkpoint-poll-interval-seconds N` for users who rely
  on `--command` to generate `relaymd-worker.json`.
- Require `--checkpoint-glob` when `--command` is supplied, or fail before upload
  with a clear error. Avoid generating a worker config with a null checkpoint
  pattern.
- If the input bundle already contains `relaymd-worker.json`, do not overwrite
  it unless `--command` is supplied, matching current behavior.
- Validate generated config before upload.

FR_ATM impact:

- FR_ATM should write `checkpoint_poll_interval_seconds: 60` into
  `relaymd-worker.json`.
- FR_ATM can remove or relax its preflight that requires the global RelayMD
  config to contain `worker_checkpoint_poll_interval_seconds: 60`.
- FR_ATM can still keep a warning if the active RelayMD version does not support
  the new bundle contract.

## Config Model Updates

Keep global `worker_checkpoint_poll_interval_seconds` as an operator default,
not a project policy.

Documentation updates:

- Explain that global worker checkpoint polling is a fallback.
- Explain that per-job bundle config takes precedence.
- Update deployment docs and example config comments accordingly.
- Avoid instructing workflow projects to carry their own repo-local
  `relaymd-config.yaml` for checkpoint polling policy.

No project-specific config layer is needed initially. The bundle contract is a
cleaner scope than “project config” because jobs can differ even within the same
project.

## Tests

Add or update tests for:

- `JobCreate(id=...)` schema and API creation.
- API rejects duplicate caller-provided job IDs.
- `relaymd submit` uploads to `jobs/{job_id}/input/bundle.tar.gz`.
- `relaymd submit` posts the same UUID it used for the upload path.
- `relaymd submit --json` emits valid JSON only on stdout.
- `relaymd submit --command ... --checkpoint-glob ... --checkpoint-poll-interval-seconds N`
  writes all three fields into generated `relaymd-worker.json`.
- `relaymd submit --command ...` without `--checkpoint-glob` fails before upload.
- Human `relaymd submit` output still remains usable.
- Worker parses `checkpoint_poll_interval_seconds` from JSON bundle config.
- Worker parses `checkpoint_poll_interval_seconds` from TOML bundle config.
- Worker rejects bundle `checkpoint_poll_interval_seconds <= 0`.
- Bundle interval overrides worker runtime default for one assigned job.
- Worker falls back to global runtime interval when bundle field is absent.
- Checkpoint download command handles success, missing checkpoint, and missing
  job.
- JSON output for list/show/status/config/path commands is stable.
- Generated OpenAPI client compiles/imports after regeneration.

## Documentation

Update:

- `README.md`
- `docs/job-lifecycle.md`
- `docs/worker-internals.md`
- `docs/deployment.md`
- `docs/cli.md`
- `docs/api-schema.md`
- `deploy/config.example.yaml`
- any FR_ATM-facing examples or test bundles in `test/`

Document:

- Canonical object storage layout.
- New `relaymd-worker.json` fields.
- JSON mode guarantees.
- Checkpoint download flow.
- Breaking change notice for development-stage users.
- The exact public checkpoint command:
  `relaymd jobs checkpoint download <job-id>`.
- The generated API client refresh step when API contracts change.

## Suggested Implementation Order

1. Canonical job ID through `JobCreate` and `relaymd submit`.
2. Regenerate OpenAPI schema/client and fix API-client call sites.
3. `relaymd submit --json`.
4. Bundle-level `checkpoint_poll_interval_seconds`.
5. Checkpoint download command.
6. JSON output for job, worker, status, config, and path commands.
7. Documentation and example updates.

This order keeps the highest-risk storage identity fix first, then gives FR_ATM
a stable automation interface, then removes the project-specific polling
workaround.
