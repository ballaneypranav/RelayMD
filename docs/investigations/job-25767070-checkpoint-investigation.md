# Investigation: Job `25767070-b6bd-47fd-8f39-5b64c098495a`

## Summary

This document captures the reported checkpoint-loss issue for job
`25767070-b6bd-47fd-8f39-5b64c098495a` and the resulting investigation.

The core finding is:

- The resumed worker did not restart from a valid checkpoint.
- The prior worker rewrote the checkpoint manifest during shutdown in a way that
  deleted missing files from the manifest.
- That behavior does not match the intended policy described during checkpointing
  design: missing files were expected to be preserved rather than deleted.
- The shutdown was consistent with the worker receiving the configured pre-timeout
  Slurm `SIGTERM`, not a hard time limit kill or OOM.

## User-Reported Symptoms

The issues described were:

- Worker `baecc959-972...` showed errors in:
  `/scratch/gilbreth/pballane/apps/relaymd-service/logs/workers/slurm-relaymd-10710934.err`
- The corresponding `out` log showed `checkpoint_file_deleted` near the end.
- When the job resumed on worker `48696ae3...`, the calculation started from
  scratch.
- All prior checkpoint data appeared to be lost.

## Files Examined

The investigation used targeted shell searches and narrow slices from these
 files:

- `/scratch/gilbreth/pballane/apps/relaymd-service/logs/workers/slurm-relaymd-10710934.out`
- `/scratch/gilbreth/pballane/apps/relaymd-service/logs/workers/slurm-relaymd-10710934.err`
- `/scratch/gilbreth/pballane/apps/relaymd-service/logs/workers/slurm-relaymd-10712042.out`
- `/scratch/gilbreth/pballane/apps/relaymd-service/logs/service/orchestrator-wrapper.log`
- `packages/relaymd-worker/src/relaymd/worker/main.py`
- `packages/relaymd-worker/tests/test_main_loop.py`
- `src/relaymd/orchestrator/templates/job.sbatch.j2`
- `packages/relaymd-core/src/relaymd/runtime_defaults.py`

## Timeline

### 1. Healthy checkpointing before shutdown

On worker `baecc959-9721-4528-9833-72fac4937803`, the last healthy checkpoint
cycle completed at:

- `2026-05-15T16:24:40.243403Z`

The worker uploaded normal checkpoint content including:

- `FOL_APT_production.log`
- `FOL_APT_stat.txt`
- `progress`
- `r13/...`
- `r14/...`

The orchestrator recorded that checkpoint immediately after:

- `2026-05-15T16:24:40.272708Z`

## 2. Final shutdown checkpoint cycle deleted manifest entries

At shutdown, the same worker logged:

- `forcing final checkpoint write`
- `skip checkpoint archive: ckpt_is_valid not present`

Immediately after that, the worker emitted a large burst of
`checkpoint_file_deleted` events for:

- `FOL_APT_production.log`
- `FOL_APT_stat.txt`
- `ckpt_is_valid`
- `progress`
- many `r*/FOL_APT.out`
- many `r*/FOL_APT.xtc`
- many `r*/FOL_APT_ckpt.xml`

This indicates that the shutdown checkpoint sync treated files that were no
longer visible in the watched paths as deletions and removed them from the
manifest state.

## 3. Worker crashed while writing the replacement manifest

The failing worker then crashed with:

```text
FileNotFoundError: [Errno 2] No such file or directory:
'/tmp/relaymd-25767070-b6bd-47fd-8f39-5b64c098495a-g81mqy8z'
```

The traceback shows the failure occurred inside:

- `relaymd.worker.main._sync_checkpoint_manifest_cycle`
- `relaymd.worker.main._atomic_write_json`

That means the worker was attempting to write the shutdown-time manifest after
the temporary working directory had disappeared.

## 4. Resumed worker hydrated only minimal files

When worker `48696ae3-19c2-4e09-a9d5-372d89460e68` resumed the job at:

- `2026-05-15T20:30:31Z`

it hydrated only:

- `FOL_APT_stat.txt`
- `progress`

It did not hydrate:

- `ckpt_is_valid`
- any `r*/FOL_APT_ckpt.xml`
- any `latest` checkpoint artifact

The resumed worker then logged:

- `no downloaded checkpoint found at ../latest`
- `starting production: python ... rbfe_production.py FOL_APT.yaml`

That is direct evidence that the resumed run started from scratch rather than
from a valid checkpoint.

## Code Findings

## Current implementation does delete missing files

The current implementation in
`packages/relaymd-worker/src/relaymd/worker/main.py` does this inside
`_sync_checkpoint_manifest_cycle(...)`:

- computes `previous_rel_paths`
- computes `current_rel_paths`
- unless `_preserve_existing_files_once` is set, removes every path in
  `previous_rel_paths - current_rel_paths`
- logs each removal as `checkpoint_file_deleted`

That means the code explicitly deletes manifest entries for files that were
previously known but are no longer present in the current watch scan.

This behavior is visible in the code block around:

- `previous_rel_paths = set(files_state.keys())`
- `current_rel_paths = {...}`
- `for deleted_rel in sorted(previous_rel_paths - current_rel_paths):`

## Preservation is only one-shot after hydration

During resume hydration, the worker sets:

- `checkpoint_manifest["_preserve_existing_files_once"] = True`

That flag is only used once. The next sync pops the flag and preserves prior
entries for that single cycle only.

After that, normal delete-on-missing behavior resumes.

So the current code implements:

- preserve hydrated entries once
- delete missing files on later cycles

It does not implement:

- never delete missing files

## Tests match the narrower behavior

The relevant test in
`packages/relaymd-worker/tests/test_main_loop.py` is:

- `test_first_checkpoint_cycle_after_hydration_keeps_manifest_entries`

That test only verifies that the first post-hydration cycle preserves
manifest-only files. It does not verify indefinite preservation and does not
assert a no-deletion policy across later cycles.

## Slurm Findings

## This does not look like a hard time-limit kill

`sacct` for Slurm job `10710934` reported:

- `State=FAILED`
- `ExitCode=1:0`
- `DerivedExitCode=0:0`
- `Elapsed=03:55:44`
- `Timelimit=04:00:00`
- `MaxRSS=2260984K`
- `ReqMem=10G`

This argues against:

- hard wall-time timeout
- out-of-memory termination

The job ended before the full wall-time limit and used far less than the
requested memory.

## This does look like the configured pre-timeout SIGTERM

The Slurm job template includes:

```text
#SBATCH --signal=TERM@{{ slurm_sigterm_margin_seconds | default(300) }}
```

The default value is:

- `DEFAULT_SLURM_SIGTERM_MARGIN_SECONDS = 300`

The job ended 256 seconds before the nominal wall-time limit, which is
consistent with receiving the configured pre-timeout `SIGTERM` slightly ahead of
the limit and then spending some time in shutdown and final checkpoint logic.

## Likely Sequence of Events

1. Slurm sent the configured early `SIGTERM` ahead of the 4-hour wall time.
2. The worker's signal handler set `shutdown_event`.
3. Shutdown logic triggered a final checkpoint cycle.
4. That final cycle ran after `ckpt_is_valid` was not present.
5. The current manifest sync logic interpreted many previously known files as
   deleted because they were missing from the current scan.
6. The worker rewrote manifest state accordingly.
7. While writing the shutdown manifest, the worker hit `FileNotFoundError`
   because the temp work directory under `/tmp/relaymd-...` was gone.
8. The next worker resumed from the damaged/truncated persisted manifest and
   found no usable downloaded checkpoint.
9. The resumed run started from scratch.

## Concrete Issues Identified

## 1. Implementation drift from intended checkpoint policy

The code currently deletes manifest entries when watched files are missing.
That is inconsistent with the stated design expectation that missing files
should never be deleted from persisted checkpoint state.

## 2. Shutdown-time checkpoint sync is unsafe

A shutdown-time sync can execute when checkpoint files are transiently absent or
when the workdir is already being torn down. That creates a destructive window
where the worker can emit mass deletions and overwrite valid manifest state.

## 3. Temp workdir lifetime is not protected during final manifest write

The final sync attempted to write to:

- `/tmp/relaymd-25767070-b6bd-47fd-8f39-5b64c098495a-g81mqy8z`

after that directory was no longer available. This means cleanup and final
manifest persistence are not safely ordered.

## 4. Resume behavior depends on manifest integrity

The resume worker relied on the persisted manifest for hydration. Once the
manifest no longer referenced checkpoint artifacts, hydration only restored
minimal files and the resumed run had no usable checkpoint.

## Recommended Follow-Up

- Change checkpoint manifest sync so missing files are not removed from
  persisted manifest state by default.
- Treat missing current-watch files during shutdown as non-destructive unless a
  strong deletion policy is explicitly intended.
- Ensure final checkpoint manifest writes happen before any cleanup of the
  worker temp directory.
- Add regression tests covering:
  - shutdown after `SIGTERM`
  - missing checkpoint files during final sync
  - manifest preservation across multiple cycles after hydration
  - resume after partial checkpoint visibility

## Conclusion

The resumed job started from scratch because the prior worker's shutdown path
deleted checkpoint entries from the manifest and then failed while writing
shutdown-time state. The current implementation supports delete-on-missing
behavior, which does not match the intended checkpoint preservation policy. The
trigger for the shutdown was most likely Slurm's configured early `SIGTERM`
before wall time, not a hard timeout or memory kill.
