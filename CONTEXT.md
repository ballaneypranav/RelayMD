# RelayMD Context Glossary

## Job Runtime Scope
`job runtime` means elapsed execution time for a single job ID only. It does not include runtime from requeued predecessor/successor job IDs.

## Runtime Seconds
`runtime_seconds` is the canonical total runtime for a job ID across all worker execution segments. For active jobs, it includes the currently open segment.

## ETC Seconds
`etc_seconds` means estimated time to completion (remaining time). It is nullable and is only defined when the job is active and progress is within `(0, 1)`.

## ETT Seconds
`ett_seconds` means estimated total time for the job instance. It is defined as `runtime_seconds + etc_seconds` when `etc_seconds` is defined; otherwise it is null.

## Runtime Source of Truth
The backend is the source of truth for runtime metrics. Frontend and CLI consume backend-provided raw seconds and do not implement independent runtime calculations.

## History vs Metrics
`job history` exists to explain event/segment timeline details. `job metrics` (`runtime_seconds`, `etc_seconds`, `ett_seconds`) are list/read API fields intended for operational views and exports.

## Live Output
`live output` means a job-produced file that RelayMD restores into the working directory and allows the payload to overwrite or append during resumed execution.

## Resume-Preserved Output
`resume-preserved output` means a job-produced file that RelayMD snapshots once immediately before a resumed execution starts, so earlier generations survive across resumes. It is not versioned on each write during a single execution segment.
Files declared as `resume-preserved output` are also part of ordinary checkpoint state for the current resumable copy; they do not need to be declared separately elsewhere.

## Preserved Output Sidecar
`preserved output sidecar` means RelayMD-managed checkpoint metadata and objects for `resume-preserved output`. It is included in checkpoint download semantics for operators, but it is not hydrated back into the worker bundle root during resume.

## Resume Segment
`resume segment` means one worker execution segment of a logical job, bounded by assignment/start and exit/handoff. RelayMD may number preserved outputs by resume segment. Payload-specific names like AToM replica directories are not resume segments.

## Handoff
`handoff` means a planned end to a resume segment where RelayMD stops the payload, preserves resumable checkpoint state, and makes the logical job eligible for another worker.

## Resumable Checkpoint State
`resumable checkpoint state` means the durable checkpoint files and manifest RelayMD may hydrate into a future resume segment.
