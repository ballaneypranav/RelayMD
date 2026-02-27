# W-167 E2E Integration Test Report

Date: `<YYYY-MM-DD>`
Operator: `<name>`
Environment: `<cluster names / orchestrator host>`
Issue: `W-167`

## Scope

Manual end-to-end validation of one RelayMD job across at least two worker handoffs, including checkpoint continuity and final completion.

## Preflight

- [ ] Orchestrator running persistently (`tmux` or systemd)
- [ ] API token confirmed (`X-API-Token`)
- [ ] Infisical secrets available to workers
- [ ] SLURM cluster config active in orchestrator config
- [ ] B2 credentials valid for upload/list/head operations

## Input Bundle

Local input bundle path: `<path>`

`relaymd-worker.json` used for this run:

```json
{
  "command": "<AToM-OpenMM command here>",
  "checkpoint_glob_pattern": "<pattern under test>"
}
```

Bundle archive creation:

```bash
tar -C "<local-input-dir>" -czf /tmp/e2e-test-001.bundle.tar.gz .
```

Upload to B2 key required by this ticket:

```bash
aws s3api put-object \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --bucket "$B2_BUCKET_NAME" \
  --key "jobs/e2e-test-001/input/" \
  --body /tmp/e2e-test-001.bundle.tar.gz
```

Initial B2 key listing:

```bash
aws s3api list-objects-v2 \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --bucket "$B2_BUCKET_NAME" \
  --prefix "jobs/e2e-test-001/" \
  --query 'Contents[].{Key:Key,Size:Size,LastModified:LastModified}'
```

## Job Registration

Create job:

```bash
JOB_JSON=$(curl -sS -X POST "$ORCHESTRATOR_URL/jobs" \
  -H "X-API-Token: $RELAYMD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"e2e-test-001","input_bundle_path":"jobs/e2e-test-001/input/"}')

JOB_ID=$(jq -r '.id' <<<"$JOB_JSON")
echo "$JOB_ID"
```

Recorded job ID: `<uuid>`

## Live Monitoring Commands

Orchestrator logs (tmux deployment):

```bash
tmux capture-pane -pt relaymd:0 -S -800 | rg "/workers/register|/jobs/request|/checkpoint|/complete|/fail|/workers/.*/heartbeat"
```

SLURM worker logs:

```bash
tail -f slurm-relaymd-<jobid>.out slurm-relaymd-<jobid>.err
```

Job state poll:

```bash
watch -n 10 "curl -sS \"$ORCHESTRATOR_URL/jobs/$JOB_ID\" -H \"X-API-Token: $RELAYMD_API_TOKEN\" | jq '{status,assigned_worker_id,latest_checkpoint_path,last_checkpoint_at,updated_at}'"
```

## Timeline

| Time (UTC) | Event | Evidence |
|---|---|---|
| `<hh:mm:ss>` | Job created | `POST /jobs` response |
| `<hh:mm:ss>` | Worker #1 submitted | `sbatch` id / scheduler log |
| `<hh:mm:ss>` | Worker #1 registered | orchestrator access log |
| `<hh:mm:ss>` | Job assigned | `POST /jobs/request` log |
| `<hh:mm:ss>` | First checkpoint uploaded | `POST /jobs/{id}/checkpoint` + B2 head |
| `<hh:mm:ss>` | Worker #1 cancelled (`scancel`) | SLURM command output |
| `<hh:mm:ss>` | Job re-queued with checkpoint path preserved | `GET /jobs/{id}` payload |
| `<hh:mm:ss>` | Worker #2 registered/assigned | orchestrator access log |
| `<hh:mm:ss>` | Worker #2 resumes from checkpoint | AToM-OpenMM step evidence |
| `<hh:mm:ss>` | Job completed | `GET /jobs/{id}` status=`completed` |

## Lifecycle Evidence

Orchestrator/API evidence commands:

```bash
curl -sS "$ORCHESTRATOR_URL/jobs/$JOB_ID" \
  -H "X-API-Token: $RELAYMD_API_TOKEN" | jq

curl -sS "$ORCHESTRATOR_URL/workers" \
  -H "X-API-Token: $RELAYMD_API_TOKEN" | jq
```

Checkpoint key verification:

```bash
aws s3api head-object \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --bucket "$B2_BUCKET_NAME" \
  --key "jobs/$JOB_ID/checkpoints/latest"
```

## Handoff Validation

Worker #1 SLURM job ID: `<id>`
Worker #2 SLURM job ID: `<id>`

Cancellation command used:

```bash
scancel <worker-1-slurm-job-id>
```

Expected/observed after cancellation:

- [ ] Job returned to `queued`/reassignable state within reaper window
- [ ] `latest_checkpoint_path` remained non-null and unchanged
- [ ] Worker #2 downloaded checkpoint and resumed

`GET /jobs/{id}` snapshots:

- Before cancel: `<json snippet>`
- After cancel/requeue: `<json snippet>`
- After reassignment: `<json snippet>`

## Step Continuity Check

| Metric | Value |
|---|---|
| Worker #1 last reported step before cancel | `<n>` |
| Worker #2 first reported step after resume | `<m>` |
| Continuity result (`m >= n` and not reset to 0) | `<pass/fail>` |

AToM-OpenMM log excerpts:

```text
<paste concise worker #1 excerpt showing final step>
<paste concise worker #2 excerpt showing resumed step>
```

## B2 Key Listing by Stage

| Stage | Command | Output summary |
|---|---|---|
| After input upload | `list-objects --prefix jobs/e2e-test-001/` | `<keys>` |
| After first checkpoint | `head/list jobs/$JOB_ID/checkpoints/` | `<keys + timestamp>` |
| After handoff | `head/list jobs/$JOB_ID/checkpoints/` | `<unchanged or updated>` |
| At completion | `list jobs/$JOB_ID/` | `<final keys>` |

## Checkpoint Glob Pattern Finalization

Patterns tested:

- `<pattern A>`
- `<pattern B>`

Final selected pattern: `<pattern>`

Reason:

`<why this pattern reliably matched AToM-OpenMM checkpoints in this run>`

## Issues Found

| Ticket | Severity | Description | Repro/Evidence |
|---|---|---|---|
| `<W-xxx>` | `<high/med/low>` | `<issue>` | `<log/link>` |

If no issues:

`No new issues were identified during this run.`

## Definition of Done Checklist

- [ ] Job completes end-to-end across at least two worker handoffs with no manual intervention between them
- [ ] Checkpoint continuity verified: second worker step count starts where first left off
- [ ] `latest_checkpoint_path` preserved in orchestrator DB across the handoff
- [ ] AToM-OpenMM checkpoint glob pattern finalized and documented
- [ ] All issues found filed as new Linear tickets
- [ ] Commit message and PR description include `fixes W-167`

## Implementation Notes (Observed During Setup)

- Worker writes checkpoints to `jobs/<job_id>/checkpoints/latest`, where `<job_id>` is the UUID returned by `POST /jobs`.
- `POST /jobs` currently accepts `title` and `input_bundle_path` only.
- Job status may remain `assigned` until terminal transition (`completed`/`failed`/`cancelled`), while checkpoint updates are still accepted in `assigned`.
- Successful Infisical fetch and Tailscale join are inferred from worker registration (`POST /workers/register`) and subsequent API activity; bootstrap code does not emit explicit success logs.
