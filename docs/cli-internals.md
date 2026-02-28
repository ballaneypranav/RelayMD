# RelayMD: Operator CLI Internals

## Framework

`typer` combined with `rich` for terminal output. Grouped into subcommands (`submit`, `jobs`, `workers`, `orchestrator`). The `main` app disables local variables in exception traces for cleaner CLI output.

## Shared Context

A dependency injection workaround using `typer.Context.obj`. The root callback initializes a `CliContext` object (containing the `CliSettings`, `StorageClient`, and `httpx.Client`) which is passed down to all subcommands. This avoids instantiating a new B2 connection for every invoked command.

## `relaymd submit` Workflow

The `submit` command is the most complex component of the CLI. It does:

1. Validates the input directory and ensures `relaymd-worker.json` or `.toml` exists (writes it if missing but `--command` is provided).
2. Generates a new `UUIDv4` for the job.
3. Streams the input directory into a `/tmp` gzip tarball using `tarfile`, skipping hidden files and `.git` via `ignore_unpacked_files()`.
4. Uploads the tarball directly to B2 via `StorageClient` using the path `jobs/{uuid}/input/bundle.tar.gz`. Shows a Rich progress bar.
5. Registers the job with the orchestrator via `POST /jobs`.

Because the upload goes directly to B2, there is no file upload proxying through the orchestrator. The CLI just tells the orchestrator where the file is.

## PyInstaller Distribution

The CLI is compiled to a static binary via PyInstaller on Linux x86_64. The build process runs inside a `manylinux2014` Docker container (via `make release-cli`) to ensure compatibility across older glibc versions (essential for CentOS/Rocky Linux HPC login nodes).

The build script strips unnecessary dependencies (like `pydantic`'s compiled cores) from the binary to reduce size.

## Token Hydration

The `CliSettings` module reads `pydantic-settings` from `~/.config/relaymd/config.yaml` and environment variables. To avoid hardcoding B2 credentials in the YAML file on the login node, the CLI supports automatic secret hydration from Infisical. If `infisical_token` is provided, the CLI will transparently fetch missing `api_token` and B2 credentials via the Infisical API before executing any command.
