# RelayMD API Schema Contract (W-138)

This document defines the HTTP contract between workers, operators, and the orchestrator.

## Shared Model Reference

Field names and types are sourced from:

- `packages/relaymd-models/src/relaymd/models/api.py`
- `packages/relaymd-models/src/relaymd/models/job.py`
- `packages/relaymd-models/src/relaymd/models/worker.py`
- `packages/relaymd-models/src/relaymd/models/enums.py`

## Authentication

- Worker-facing endpoints require `X-API-Token: <RELAYMD_API_TOKEN>`.
- Worker-facing endpoints:
  - `POST /workers/register`
  - `POST /workers/{worker_id}/heartbeat`
  - `POST /workers/{worker_id}/deregister`
  - `POST /jobs/request`
  - `POST /jobs/{job_id}/checkpoint`
  - `POST /jobs/{job_id}/complete`
  - `POST /jobs/{job_id}/fail`

## Type Definitions

### WorkerRegister

- `platform: Platform` (`"hpc"` | `"salad"`)
- `gpu_model: str`
- `gpu_count: int`
- `vram_gb: int`

### WorkerRead

- `id: UUID`
- `platform: Platform`
- `gpu_model: str`
- `gpu_count: int`
- `vram_gb: int`
- `last_heartbeat: datetime`

### JobCreate

- `title: str`
- `input_bundle_path: str`

### JobRead

- `id: UUID`
- `title: str`
- `status: JobStatus` (`"queued"` | `"assigned"` | `"running"` | `"completed"` | `"failed"` | `"cancelled"`)
- `input_bundle_path: str`
- `latest_checkpoint_path: str | null`
- `last_checkpoint_at: datetime | null`
- `assigned_worker_id: UUID | null`
- `created_at: datetime`
- `updated_at: datetime`

### CheckpointReport

- `checkpoint_path: str`

### JobAssigned

- `status: Literal["assigned"]`
- `job_id: UUID`
- `input_bundle_path: str`
- `latest_checkpoint_path: str | null`

### NoJobAvailable

- `status: Literal["no_job_available"]`

## Endpoint Contract

### 1) POST `/workers/register`

- Auth: `X-API-Token` required
- Request body: `WorkerRegister`
- Response body (`200 OK`):
  - `worker_id: UUID`
- Status codes:
  - `200 OK` worker registered
  - `401 Unauthorized` invalid/missing API token
  - `422 Unprocessable Entity` validation error

### 2) POST `/workers/{worker_id}/heartbeat`

- Auth: `X-API-Token` required
- Path params:
  - `worker_id: UUID`
- Request body: none
- Response body: none
- Status codes:
  - `204 No Content` heartbeat accepted
  - `401 Unauthorized` invalid/missing API token
  - `404 Not Found` unknown worker

### 3) POST `/workers/{worker_id}/deregister`

- Auth: `X-API-Token` required
- Path params:
  - `worker_id: UUID`
- Request body: none
- Response body: none
- Status codes:
  - `204 No Content` worker deregistered
  - `401 Unauthorized` invalid/missing API token
  - `404 Not Found` unknown worker

### 4) POST `/jobs/request`

- Auth: `X-API-Token` required
- Request body: none
- Response body (`200 OK`): `JobAssigned | NoJobAvailable`
  - `JobAssigned` fields:
    - `status: "assigned"`
    - `job_id: UUID`
    - `input_bundle_path: str`
    - `latest_checkpoint_path: str | null`
  - `NoJobAvailable` fields:
    - `status: "no_job_available"`
- Status codes:
  - `200 OK` with one of the above response shapes
  - `401 Unauthorized` invalid/missing API token

### 5) POST `/jobs/{job_id}/checkpoint`

- Auth: `X-API-Token` required
- Path params:
  - `job_id: UUID`
- Request body: `CheckpointReport`
- Response body: none
- Status codes:
  - `204 No Content` checkpoint recorded
  - `401 Unauthorized` invalid/missing API token
  - `404 Not Found` unknown job
  - `422 Unprocessable Entity` validation error

### 6) POST `/jobs/{job_id}/complete`

- Auth: `X-API-Token` required
- Path params:
  - `job_id: UUID`
- Request body: none
- Response body: none
- Status codes:
  - `204 No Content` job marked complete
  - `401 Unauthorized` invalid/missing API token
  - `404 Not Found` unknown job

### 7) POST `/jobs/{job_id}/fail`

- Auth: `X-API-Token` required
- Path params:
  - `job_id: UUID`
- Request body: none
- Response body: none
- Status codes:
  - `204 No Content` job marked failed
  - `401 Unauthorized` invalid/missing API token
  - `404 Not Found` unknown job

### 8) POST `/jobs`

- Request body: `JobCreate`
- Response body (`201 Created`): `JobRead`
- Status codes:
  - `201 Created` job created
  - `422 Unprocessable Entity` validation error

### 9) GET `/jobs`

- Request body: none
- Response body (`200 OK`): `list[JobRead]`
- Status codes:
  - `200 OK`

### 10) GET `/jobs/{job_id}`

- Path params:
  - `job_id: UUID`
- Request body: none
- Response body (`200 OK`): `JobRead`
- Status codes:
  - `200 OK`
  - `404 Not Found` unknown job

### 11) DELETE `/jobs/{job_id}`

- Path params:
  - `job_id: UUID`
- Query params:
  - `force: bool = false`
- Request body: none
- Response body: none
- Status codes:
  - `204 No Content` cancelled (or force-cancelled)
  - `404 Not Found` unknown job
  - `409 Conflict` job is running and `force` is not `true`

### 12) GET `/healthz`

- Request body: none
- Response body (`200 OK`):
  - `status: "ok"`
- Status codes:
  - `200 OK`
