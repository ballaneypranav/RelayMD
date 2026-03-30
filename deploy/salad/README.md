# Salad Cloud Deployment (W-156)

This runbook validates RelayMD worker deployment on Salad Cloud using the GHCR
image from `W-150`, with secrets injected via Salad environment variables.

## Image and Container Group

1. In Salad Cloud, create a new container group.
2. Container image:
   - `ghcr.io/<org>/relaymd-worker:latest`
3. Replica count:
   - start at `0`
4. GPU selection:
   - choose GPUs with `>=16GB` VRAM
   - preferred tiers: `RTX 4090`, `A5000`, `A6000`

## Required Environment Variables

Set these in the Salad dashboard:

- `INFISICAL_TOKEN=<client_id>:<client_secret>`
- `WORKER_PLATFORM=salad`

Current worker runtime compatibility notes:

- Salad does not expand `${...}` references in env-var values.
- If you keep `INFISICAL_BOOTSTRAP_TOKEN` for compatibility with old runbooks, set `INFISICAL_TOKEN` to the same literal value.

Optional runtime tuning env vars:
- `HEARTBEAT_INTERVAL_SECONDS` (default `60`)
- `CHECKPOINT_POLL_INTERVAL_SECONDS` (default `300`)
- `ORCHESTRATOR_TIMEOUT_SECONDS` (default `30.0`)

## Bring-Up and Validation Steps

1. Scale replicas from `0` to `1`.
2. Watch Salad container logs and orchestrator logs.
3. Confirm Infisical bootstrap succeeds (no token parsing/fetch errors).
4. Confirm Tailscale join succeeds:
   - a new ephemeral node appears in the Tailscale admin panel
5. Confirm orchestrator registration:
   - `POST /workers/register` is logged by orchestrator
6. Confirm worker record from orchestrator API:
   - `GET /workers` shows new worker with:
     - `platform="salad"`
     - expected `gpu_model`
     - expected `vram_gb`

Example check:

```bash
curl -sS -H "X-API-Token: $RELAYMD_API_TOKEN" http://<orchestrator-host>:36158/workers
```

## Salad GPU Model String Capture (for W-158)

If `gpu_model` or `vram_gb` is unexpected, capture exact model strings returned
by NVML on Salad nodes and record below.

Observed model strings:

- `<fill from worker/orchestrator logs>`
- `<fill from worker/orchestrator logs>`

## Scale-Down Verification

1. Scale replicas back from `1` to `0` after validation.
2. Confirm the node disappears from Tailscale admin panel within a few minutes
   (ephemeral key behavior).

## Validation Record Template

Fill this after the live run:

- Date/time:
- Salad container group name:
- Image digest/tag:
- Replica scale-up time:
- Tailscale node name:
- `/workers` observed `platform`:
- `/workers` observed `gpu_model`:
- `/workers` observed `vram_gb`:
- `/healthz` reachability notes:
- Ephemeral node disappearance verified (yes/no + timestamp):
- Final status:
