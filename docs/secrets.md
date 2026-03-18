# Security Internals

RelayMD uses [Infisical](https://infisical.com/) as the single source of truth for runtime
secrets.

## Bootstrap Model

Only one secret is expected to be externally provided:
- `INFISICAL_TOKEN` (machine identity token, `<client_id>:<client_secret>`)

`INFISICAL_TOKEN` must be present in the process environment and valid for the configured
Infisical workspace/environment.

All other secret values are fetched from Infisical during process startup or worker bootstrap.

## Secrets Stored in Infisical

Primary runtime secrets:
- `RELAYMD_API_TOKEN`
- `AXIOM_TOKEN`
- `B2_APPLICATION_KEY`
- `B2_APPLICATION_KEY_ID`
- `B2_ENDPOINT`
- `BUCKET_NAME`
- `DOWNLOAD_BEARER_TOKEN` (optional)
- `RELAYMD_ORCHESTRATOR_URL`
- `TAILSCALE_AUTH_KEY`

Additional infra-level secrets (currently not consumed by core Python runtime):
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

## Current Propagation Behavior

### Orchestrator

`src/relaymd/orchestrator/config.py` requires `INFISICAL_TOKEN` and hydrates required secrets
from Infisical. Orchestrator startup fails fast when the token is missing/invalid or when
required hydrated values are missing.

### SLURM worker launch template

`src/relaymd/orchestrator/templates/job.sbatch.j2` injects only the bootstrap secret:
- `INFISICAL_BOOTSTRAP_TOKEN`
- `INFISICAL_TOKEN` (mapped from bootstrap token)

No additional API/B2/Tailscale/Axiom secrets are injected into the template environment.

### Worker runtime bootstrap (HPC + Salad)

`packages/relaymd-worker/src/relaymd/worker/bootstrap.py` uses `INFISICAL_TOKEN` to fetch worker
runtime secrets from Infisical (B2 credentials, API token, orchestrator URL, Tailscale auth key,
optional download bearer token, and Axiom token).

### CLI

`src/relaymd/cli/config.py` requires `INFISICAL_TOKEN` and hydrates API + B2 secrets from
Infisical before use. CLI startup fails fast when the token is missing/invalid or when required
hydrated values are missing. The optional download bearer token is also read from Infisical when
present.

## Security Notes

- Secret loading follows a fail-fast model: missing bootstrap token or missing required hydrated
	secrets causes startup/config load failure.

## Limitations / Operational Caveats

- For `docker://` Apptainer pulls from private registries on SLURM login/submit hosts, host-level
	registry authentication is not currently injected by the template. Ensure image access strategy is
	compatible with your cluster environment.
- Token rotation for long-running workloads is not yet implemented.
