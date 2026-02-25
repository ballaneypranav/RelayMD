# RelayMD API Client

This package contains typed client code generated from the orchestrator OpenAPI schema.
Generated artifacts are intentionally not committed; regenerate after API contract changes.

## Regenerate

From repository root:

```bash
./scripts/sync_workspace.sh
```

Or generate just the schema + client:

```bash
./scripts/generate_api_client.sh
```

The generator uses `relaymd.orchestrator.main:create_app` as the OpenAPI source.
