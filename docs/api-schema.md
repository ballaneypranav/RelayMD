# API Schema Source of Truth

The orchestrator and worker share API payload models from the `relaymd.models` package.

Current source files:

- `packages/relaymd-core/src/relaymd/models/api.py`
- `packages/relaymd-core/src/relaymd/models/job.py`
- `packages/relaymd-core/src/relaymd/models/worker.py`
- `packages/relaymd-core/src/relaymd/models/enums.py`

When adding or changing API fields, update these models first, then regenerate any downstream documentation/examples if needed.
