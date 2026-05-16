# ADR 0003: Planned Worker Handoff Before Allocation Deadline

RelayMD will model planned worker exits as a first-class `handoff` state rather than inferring resumable interruptions from worker disappearance, Slurm signals, or failure reports. A worker approaching a known allocation deadline will report `handoff/start`, stop the payload, perform a non-destructive final checkpoint sync, report `handoff/complete`, and then deregister and exit with status code `0`; `handoff/complete` atomically records the final checkpoint observation and moves the logical job back to `queued` for the next worker. This keeps payload completion, payload failure, and resumable infrastructure handoff distinct while avoiding the destructive and ambiguous shutdown behavior seen when Slurm `SIGTERM` is the primary control path.

## Status
Accepted

## Consequences
- `handoff` is an operator-visible job status between `running` and `queued`.
- `handoff/start` carries intent and current progress, but no final checkpoint claim.
- `handoff/complete` may requeue from the previous resumable checkpoint state when no newer valid checkpoint is produced.
- SLURM wrappers inject allocation deadline and proactive handoff margin into the worker; the default target is to start handoff 600 seconds before the deadline while preserving `TERM@300` as a fallback.
- Missing files during checkpoint sync are not deletion evidence for resumable checkpoint state.

## Considered Options
1. Continue relying on Slurm `SIGTERM` and stale-worker requeue.
   - Rejected because it makes a planned handoff indistinguishable from crash cleanup and leaves final checkpointing inside the scheduler signal window.
2. Reuse `completed` or `failed` for worker allocation end.
   - Rejected because those describe payload outcome, not a resumable worker segment boundary.
3. Requeue immediately at `handoff/start`.
   - Rejected because the old worker may still be stopping the payload and uploading checkpoint state, creating a risk of two workers running the same logical job.
