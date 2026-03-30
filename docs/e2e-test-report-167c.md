# W-195 E2E Test Report

## Summary

- Linear issue: `W-195`
- Validation target: worker handoff with checkpoint continuity using the dummy checkpoint workload
- Bundle used: `test/checkpoint-handoff`
- Job ID: `d8730b48-c157-4c1b-a4bc-83b0d073c4c3`
- Result: passed with one follow-up issue

This run validated that a job cancelled mid-run resumed on a second worker from the latest persisted checkpoint rather than restarting from iteration `0`. The orchestrator preserved `latest_checkpoint_path`, worker #2 downloaded the checkpoint, and the resumed job completed successfully.

## Test Setup

- RelayMD orchestrator running on `http://127.0.0.1:36158`
- Worker bootstrap orchestrator URL from worker logs:
  `http://relaymd-orchestrator:36158`
- Dummy bundle:
  - `run.sh` writes `checkpoint.chk` every 60 seconds for 8 total iterations
  - if `../latest` exists, `run.sh` reads `iteration=<n>` and resumes from `n + 1`
  - `relaymd-worker.json` sets `checkpoint_glob_pattern` to `*.chk`
- Local test config:
  - `worker_checkpoint_poll_interval_seconds: 60`

## Timeline

- `2026-03-30T23:32:41.253197Z`: job `d8730b48-c157-4c1b-a4bc-83b0d073c4c3` created with title `checkpoint-handoff`
- `2026-03-30T23:33:09.755406Z`: worker #1 placeholder submitted as SLURM job `10493040`
- `2026-03-30T23:33:19.650358Z`: worker #1 (`248ed54b-d111-46c8-8937-388bdc77053f`) assigned the job
- `2026-03-30T23:34:20.234946Z`: first checkpoint recorded
- `2026-03-30T23:35:20.272694Z`: second checkpoint recorded
- `2026-03-30T23:36:20.394367Z`: third checkpoint recorded
- `2026-03-30T23:37:20.222746Z`: fourth checkpoint recorded
- `2026-03-30T23:37:26Z`: SLURM cancelled worker #1
- `2026-03-30T23:40:29.467647Z`: worker #2 placeholder submitted as SLURM job `10493069`
- `2026-03-30T23:40:44.683003Z`: worker #2 (`125c2c80-b51d-474a-900e-bdaaa02db335`) assigned the same job
- `2026-03-30T23:41:45.409067Z`: resumed checkpoint recorded from worker #2
- `2026-03-30T23:42:45.567627Z`: additional resumed checkpoint recorded
- `2026-03-30T23:43:45.322072Z`: final checkpoint recorded
- `2026-03-30T23:43:45.356007Z`: job completion reported

## Evidence

### Worker #1 logs

```text
relaymd checkpoint handoff test start: 2026-03-30T23:33:20Z
hostname: gilbreth-h014.rcac.purdue.edu
writing checkpoint.chk up to iteration 8 every 60s
no downloaded checkpoint found; starting from iteration 0
checkpoint write 1/8: 2026-03-30T23:33:20Z
checkpoint write 2/8: 2026-03-30T23:34:20Z
checkpoint write 3/8: 2026-03-30T23:35:20Z
checkpoint write 4/8: 2026-03-30T23:36:20Z
checkpoint write 5/8: 2026-03-30T23:37:20Z
[2026-03-30T19:37:26.096] error: *** JOB 10493040 ON gilbreth-h014 CANCELLED AT 2026-03-30T19:37:26 DUE to SIGNAL Terminated ***
```

This confirms worker #1 started from scratch and was terminated mid-run after writing iteration `5`.

### Orchestrator checkpoint persistence

Relevant orchestrator log events for job `d8730b48-c157-4c1b-a4bc-83b0d073c4c3`:

```text
2026-03-30T23:34:20.234946Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=248ed54b-d111-46c8-8937-388bdc77053f
2026-03-30T23:35:20.272694Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=248ed54b-d111-46c8-8937-388bdc77053f
2026-03-30T23:36:20.394367Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=248ed54b-d111-46c8-8937-388bdc77053f
2026-03-30T23:37:20.222746Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=248ed54b-d111-46c8-8937-388bdc77053f
```

This shows `latest_checkpoint_path` became non-null during worker #1 execution and remained pointed at:

```text
jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest
```

### Worker #2 logs

```text
relaymd checkpoint handoff test start: 2026-03-30T23:40:45Z
hostname: gilbreth-k042.rcac.purdue.edu
writing checkpoint.chk up to iteration 8 every 60s
resuming from checkpoint iteration 4 via ../latest
checkpoint write 5/8: 2026-03-30T23:40:45Z
checkpoint write 6/8: 2026-03-30T23:41:45Z
checkpoint write 7/8: 2026-03-30T23:42:45Z
checkpoint write 8/8: 2026-03-30T23:43:45Z
relaymd checkpoint handoff test end: 2026-03-30T23:43:45Z
{"worker_id":"125c2c80-b51d-474a-900e-bdaaa02db335","event":"no_job_available_worker_exit","level":"info","timestamp":"2026-03-30T23:43:45.378645Z"}
```

This is the key continuity proof:

- worker #2 saw a downloaded checkpoint at `../latest`
- worker #2 resumed from iteration `4`
- the next emitted iteration was `5/8`, not `1/8`

The resumed worker starting from `4` instead of `5` is consistent with cancellation landing shortly after the local write of iteration `5` but before that checkpoint was uploaded and persisted.

### Reassignment and completion

Relevant orchestrator log events for the resumed worker:

```text
2026-03-30T23:40:44.683003Z job_assignment_succeeded worker_id=125c2c80-b51d-474a-900e-bdaaa02db335 provider_id=gilbreth-standby-a100-80gb:10493069
2026-03-30T23:41:45.409067Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=125c2c80-b51d-474a-900e-bdaaa02db335
2026-03-30T23:42:45.567627Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=125c2c80-b51d-474a-900e-bdaaa02db335
2026-03-30T23:43:45.322072Z checkpoint_recorded latest_checkpoint_path=jobs/d8730b48-c157-4c1b-a4bc-83b0d073c4c3/checkpoints/latest worker_id=125c2c80-b51d-474a-900e-bdaaa02db335
2026-03-30T23:43:45.356007Z job_completed_reported worker_id=125c2c80-b51d-474a-900e-bdaaa02db335
```

This confirms the checkpoint path stayed stable across the handoff and that the resumed job completed successfully.

## Dashboard Observation During Handoff

One dashboard snapshot taken after the first worker was cancelled showed:

```text
job_id               title               status    age     time_in_status assigned_worker_id                    time_since_checkpoint
d8730b48...          checkpoint-handoff  assigned  5m 46s  1m 7s          248ed54b-d111-46c8-8937-388bdc77053f 1m 7s
```

That observation shows the job remained `assigned` for at least part of the recovery window even after worker #1 had already been terminated.

## Definition of Done Check

- [x] `latest_checkpoint_path` preserved across handoff in orchestrator DB
- [x] Worker #2 logs show checkpoint download/resume behavior, not just input bundle execution
- [x] Dummy script output confirms resume from correct state rather than restart
- [x] Job completes as `completed` after worker #2 finishes
- [x] `docs/e2e-test-report-167c.md` added with timeline and log excerpts from both workers
- [ ] B2 key listing captured at each stage
- [ ] Follow-up tickets filed for issues found
- [ ] Commit message and PR include `fixes W-167c`

## Issues Found

### Reassignment latency exceeded the target handoff window

Worker #1 was cancelled at `2026-03-30T23:37:26Z`, but worker #2 was not assigned until `2026-03-30T23:40:44.683003Z`, roughly `3m 19s` later. A dashboard snapshot during that gap still showed the job as `assigned` to worker #1 rather than already `queued`.

Impact:

- checkpoint continuity worked once reassignment happened
- the handoff recovery path appears slower than the desired "within 2× heartbeat interval" behavior

Recommended follow-up:

- file a new ticket to investigate stale-worker detection and reassignment latency after abrupt worker termination

## Conclusion

W-195 runtime validation succeeded for checkpoint continuity. The dummy workload resumed on worker #2 from the persisted checkpoint at iteration `4`, continued at iteration `5`, and completed successfully with `latest_checkpoint_path` preserved across the handoff. The main remaining issue is reassignment latency after worker cancellation, not checkpoint resume correctness.
