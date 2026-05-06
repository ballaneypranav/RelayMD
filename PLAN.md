# Move Payload Supervision Into RelayMD Python Worker

## Summary

The stuck job happened because RelayMD only watches the top-level bundle command. For the current AToM bundle, that command is:

`/scratch/gilbreth/pballane/folate-alpha-beta/FR_ATM-LSFE-00-wibowo2013/output/07-production-relaymd-bundles/APT_FOL/run.sh`

That script launches `python rbfe_production.py APT_FOL.yaml`. An internal OpenMM multiprocessing child crashed, but the parent AToM process stayed alive, so `run.sh` kept waiting and RelayMD left the job assigned. Move generic supervision into `packages/relaymd-worker/src/relaymd/worker/job_execution.py` so every bundle gets process-group cleanup, timeout handling, progress detection, and failure reporting.

## Key Changes

- Extend bundle config parsing in `packages/relaymd-worker/src/relaymd/worker/main.py`:
  - Keep existing fields: `command`, `checkpoint_glob_pattern`, `checkpoint_poll_interval_seconds`.
  - Add optional fields: `progress_glob_pattern`, `startup_progress_timeout_seconds`, `progress_timeout_seconds`, `max_runtime_seconds`, `fatal_log_path`, `fatal_log_patterns`.
  - Support JSON/TOML in existing `relaymd-worker.json` / `.toml` files.
- Update process supervision in `packages/relaymd-worker/src/relaymd/worker/job_execution.py`:
  - Start bundle commands in a new process group/session.
  - Send TERM/KILL to the whole process group, not only the top PID.
  - Track top-level exit code as today.
  - Add supervision failure reasons for max runtime, startup no-progress, stalled progress, and fatal log match.
- Update `_run_assigned_job` in `packages/relaymd-worker/src/relaymd/worker/main.py`:
  - Call supervision checks inside the existing polling loop.
  - On supervision failure, terminate/kill the process group, perform final checkpoint handling, then call `gateway.fail_job`.
  - Preserve existing SIGTERM checkpoint handoff behavior.

## Bundle And Example Paths

- Current AToM bundle wrapper:
  - `/scratch/gilbreth/pballane/folate-alpha-beta/FR_ATM-LSFE-00-wibowo2013/output/07-production-relaymd-bundles/APT_FOL/run.sh`
- Current AToM bundle worker config:
  - `/scratch/gilbreth/pballane/folate-alpha-beta/FR_ATM-LSFE-00-wibowo2013/output/07-production-relaymd-bundles/APT_FOL/relaymd-worker.json`
- AToM bundle output/log watched by supervision:
  - `APT_FOL_production.log`
  - `ckpt_is_valid`
  - `progress`
  - `r*/APT_FOL.out`
  - `r*/APT_FOL_ckpt.xml`
  - `relaymd-checkpoint.tar.gz`

For AToM-generated bundles, keep `run.sh` as a thin domain adapter: resolve `ATS_DIR`, create `nodefile`, restore latest checkpoint, run production, and create `relaymd-checkpoint.tar.gz`. Do not put generic timeout/log/progress supervision in `run.sh`.

The generated `relaymd-worker.json` for AToM should include supervision fields similar to:

```json
{
  "command": ["bash", "run.sh"],
  "checkpoint_glob_pattern": "relaymd-checkpoint.tar.gz",
  "checkpoint_poll_interval_seconds": 60,
  "progress_glob_pattern": [
    "ckpt_is_valid",
    "progress",
    "r*/APT_FOL.out",
    "r*/APT_FOL_ckpt.xml"
  ],
  "startup_progress_timeout_seconds": 900,
  "progress_timeout_seconds": 1800,
  "fatal_log_path": "APT_FOL_production.log",
  "fatal_log_patterns": [
    "Traceback",
    "CUDA_ERROR",
    "Segmentation fault",
    "Aborted",
    "Killed"
  ]
}
```

## Tests

- Add worker execution tests under `packages/relaymd-worker/tests/test_main_loop.py` or a new focused `test_job_execution.py`:
  - Nonzero top-level process marks failed.
  - Hung parent with fatal log pattern is killed and marked failed.
  - Startup progress timeout kills process group and marks failed.
  - Progress timeout resets when matching file mtime advances.
  - TERM/KILL reaches child processes, not only the shell wrapper.
  - Existing configs without supervision fields still work.
- Add config parsing tests for JSON and TOML supervision fields.
- Update docs:
  - `docs/worker-internals.md`
  - `docs/job-lifecycle.md`
  - `docs/cli.md` `relaymd-worker.json` section
  - optionally `docs/deployment.md` if AToM bundle generation defaults are documented there.

## Assumptions

- Supervision fields are optional and backward compatible.
- Progress and fatal-log supervision are opt-in per bundle to avoid false positives for arbitrary workloads.
- RelayMD worker remains domain-neutral; AToM-specific file names belong only in generated bundle config.
- Orchestrator heartbeat logic should not infer payload health. A live worker can still be supervising a hung or failed payload, so failure detection belongs in the worker.

