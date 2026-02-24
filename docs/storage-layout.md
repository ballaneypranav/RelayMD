# B2 Bucket Key Layout Design Document

This document defines the canonical B2 bucket key structure for RelayMD. Both the orchestrator and workers must strictly adhere to these paths to ensure consistency and a stable contract across all components.

## Key Paths

The B2 bucket relies on the following structural layout:

- `jobs/{job_id}/input/` 
  This path holds the immutable input bundle uploaded exactly once by the user prior to job creation. The contents within this path are never overwritten.

- `jobs/{job_id}/checkpoints/latest` 
  This path houses a single checkpoint file. It is uniquely designed to be continually overwritten by the latest worker checkpoint in real-time. The orchestrator tracks state by storing solely this key path in its database.

**Note on `{job_id}`**: 
The `{job_id}` parameter represents the true UUID matching the `jobs` table primary key in the backing database.

## Architecture Guidelines

- **Read vs Write Endpoints**: The Cloudflare Worker URL (established in W-136) must be treated as the absolute canonical read endpoint for all object downloads. Direct B2 S3 API URLs are exclusively reserved for writes.
- **Checkpoint Detection**: The glob pattern used for actual checkpoint file detection (e.g., `*.chk`) within the `/checkpoints` directory will be finalized during end-to-end testing (ticket W-167).

## Read Endpoint

- **Base URL**: `https://cloudflare-backblaze-worker.pranav-purdue-account.workers.dev`
- **Route**: `/files/<object-key>`
- **Auth**: `Authorization: Bearer <DOWNLOAD_BEARER_TOKEN>` (value sourced from Infisical in the RelayMD secrets path)
