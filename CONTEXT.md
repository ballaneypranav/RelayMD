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
