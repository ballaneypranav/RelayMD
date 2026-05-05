# RelayMD: Operator CLI Internals

## Framework

`typer` combined with `rich` for terminal output. Grouped into service commands (`up`, `down`, `restart`, `status`, `logs`, `attach`, `upgrade`) and operator subcommands (`submit`, `jobs`, `workers`, `monitor`, `path`, `config`). Singular `job`/`worker` remain hidden compatibility aliases. Low-level `orchestrator` commands remain hidden.

## Shared Context

A dependency injection workaround using `typer.Context.obj`. The root callback initializes a `CliContext` object (containing the `CliSettings`, `StorageClient`, and `httpx.Client`) which is passed down to API-facing subcommands. This avoids instantiating a new B2 connection for every invoked command.

## `relaymd submit` Workflow

The `submit` command is the most complex component of the CLI. It does:

1. Validates the input directory and ensures `relaymd-worker.json` or `.toml` exists (or writes it when `--command` is provided).
2. Generates one canonical `UUIDv4` for the job.
3. Streams the input directory into a `/tmp` gzip tarball using `tarfile`.
4. Uploads the tarball directly to B2 via `StorageClient` at `jobs/{job_id}/input/bundle.tar.gz`.
5. Registers the job with the orchestrator via `POST /jobs` with the same `id={job_id}`.

Because the upload goes directly to B2, there is no file upload proxying through the orchestrator. The CLI just tells the orchestrator where the file is.

JSON mode (`--json`) is supported for automation-facing commands. In JSON mode, stdout is reserved for JSON payloads.

## Cross-Host API Command Dispatch

On module-managed HPC installs, the service status file identifies the host that
owns the active RelayMD service lock. API-backed operator commands (`submit`,
`jobs`, `workers`, and `monitor`, including hidden singular aliases) check this
status before executing. If the current shell is on a different login node and
the locked host has fresh orchestrator and proxy heartbeats, the CLI re-executes
the same command on the locked host with SSH and exits with the remote command's
status code.

The remote command changes to the original working directory and uses the same
RelayMD executable path when possible. Before invoking the executable, it sources
the configured module-managed service env file when present so secret hydration
inputs are available on the remote login node. stdout and stderr are not wrapped,
so JSON mode remains machine-readable. An internal
`RELAYMD_CLI_REMOTE_DISPATCH=1` environment variable prevents recursive
delegation on the remote host.

Commands that manage or inspect the local service process (`up`, `down`,
`restart`, `status`, `logs`, `attach`, `upgrade`) are not SSH-delegated.
`relaymd status` has its own remote path: when invoked off-host, the HPC status
wrapper SSHes to the locked service host and runs the same status check there
with `RELAYMD_STATUS_REMOTE_CHECK=1` to avoid recursion.

## Status Readiness Diagnostics

`relaymd status` combines wrapper-level process health with Python readiness
diagnostics from the hidden `relaymd config diagnose --json` command. The
diagnostics command validates the resolved env/config paths, performs live
Infisical hydration for CLI and orchestrator settings, and reports redacted
readiness for submit credentials, service secrets, release assets, proxy auth,
SLURM access, configured SIF paths, the Tailscale socket, and the database URL.
Secret values are never printed.

In JSON mode, status preserves the existing process fields and adds
`readiness_ok` plus a `readiness` object. Overall `healthy` requires both process
health and readiness to pass.

## PyInstaller Distribution

The CLI is compiled to a static binary via PyInstaller on Linux x86_64. The build process runs inside a `manylinux2014` Docker container (via `make release-cli`) to ensure compatibility across older glibc versions (essential for CentOS/Rocky Linux HPC login nodes).

The build script strips unnecessary dependencies (like `pydantic`'s compiled cores) from the binary to reduce size.

## Token Hydration

The `CliSettings` module reads `pydantic-settings` from `RELAYMD_CONFIG`, or from
`$RELAYMD_DATA_ROOT/config/relaymd-config.yaml` in the module-managed HPC install.
When neither env var is set, standalone fallback paths are
`~/.config/relaymd/config.yaml` and then `./relaymd-config.yaml`.
`INFISICAL_TOKEN` is env-only and is intentionally ignored in YAML; for HPC
service installs it belongs in `$RELAYMD_DATA_ROOT/config/relaymd-service.env`.
The CLI then hydrates missing `api_token` and B2 credentials via Infisical
before executing commands.
