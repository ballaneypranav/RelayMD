# API Schema Source of Truth

The orchestrator's OpenAPI schema is exported from `relaymd.orchestrator.main:create_app`.

Shared payload model definitions are still maintained in `relaymd.models`:

- `packages/relaymd-core/src/relaymd/models/api.py`
- `packages/relaymd-core/src/relaymd/models/job.py`
- `packages/relaymd-core/src/relaymd/models/worker.py`
- `packages/relaymd-core/src/relaymd/models/enums.py`

Typed client code for CLI/worker is generated into:

- `packages/relaymd-api-client/src/relaymd_api_client/`

The generated package source is not committed. Regenerate it whenever API contracts change.

Transition-sensitive endpoints now also expose a typed `409` payload (`JobConflict`) for invalid
or stale state transitions.

`JobCreate` accepts an optional caller-provided `id`. RelayMD CLI submit uses this to make one canonical job ID span:

- orchestrator DB row identity
- bundle object path `jobs/{job_id}/input/bundle.tar.gz`
- checkpoint object path `jobs/{job_id}/checkpoints/latest`

Bootstrap workspace (recommended):

```bash
./scripts/sync_workspace.sh
```

Regenerate schema + client only:

```bash
./scripts/generate_api_client.sh
```

When adding or changing API fields, update shared models and router contracts first, then regenerate the client package.
