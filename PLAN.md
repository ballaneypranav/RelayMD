### HPC Deploy Reliability + Auto-Tag Pull Plan

#### Summary
Implement a reliability-focused HPC deploy update on a new branch, with these explicit goals:
1. `relaymd-service-pull` can auto-resolve image tags (no GitHub copy/paste).
2. Service startup failures are diagnosable from persistent logs.
3. Status reflects live reality (heartbeat + exit metadata), not just last start.
4. Existing frontend tmux model remains primary (no Slurm service-mode migration in this change).

#### Implementation Changes
1. **Branch and scope setup**
- Create branch from `main`: `hpc-service-reliability`.
- Keep existing wrapper names and backward-compatible CLI behavior where possible.
- Keep tmux-on-frontend as primary runtime model.

2. **Automate SHA tag resolution in pull step**
- Extend `relaymd-service-pull` interface:
  - Keep current mode: explicit URIs still supported.
  - Add auto mode: if URIs are omitted, resolve them automatically.
  - Add `latest` release selector: `relaymd-service-pull latest` resolves newest shared `sha-*` across orchestrator + worker packages.
- Resolution policy (locked choice):
  - Choose **latest shared SHA tag** present in both GHCR packages.
- Owner/registry defaults:
  - `RELAYMD_GHCR_OWNER` optional override.
  - Default owner from `gh repo view --json owner -q .owner.login`.
  - Package names fixed to `relaymd-orchestrator` and `relaymd-worker`.
- Dependencies/failure behavior:
  - Require `gh` and `jq` only for auto-latest mode.
  - Require `gh` auth scope `read:packages`.
  - Emit actionable errors with exact remediation command.
- Preserve existing release safety checks (path-safe release name, symlink protections, scratch temp/cache).

3. **Service death troubleshooting + persistent logging**
- Add persistent wrapper-level logs under `/depot/.../logs/service/`:
  - `orchestrator-wrapper.log`
  - `proxy-wrapper.log`
- Run tmux pane commands through a small supervised shell wrapper that:
  - appends stdout/stderr to the corresponding wrapper log,
  - writes start timestamp, command, host, and image path,
  - writes exit timestamp and exit code on termination.
- Startup verification:
  - After `tmux respawn-pane`, wait briefly (`STARTUP_GRACE_SECONDS`, default 3).
  - If pane/session exits early, print a concise failure summary and tail of wrapper log to terminal.

4. **Heartbeat + truthful status metadata**
- Extend shared status file schema to include:
  - `ORCHESTRATOR_HEARTBEAT_AT`, `PROXY_HEARTBEAT_AT`
  - `ORCHESTRATOR_LAST_START_AT`, `ORCHESTRATOR_LAST_EXIT_AT`, `ORCHESTRATOR_LAST_EXIT_CODE`
  - `PROXY_LAST_START_AT`, `PROXY_LAST_EXIT_AT`, `PROXY_LAST_EXIT_CODE`
- Heartbeat mechanism:
  - While each service process is alive, update heartbeat timestamp every `RELAYMD_HEARTBEAT_INTERVAL_SECONDS` (default 30).
  - On process exit, mark corresponding `*_ACTIVE=0` and set exit metadata.
- Lock behavior refinement:
  - Keep cross-host lock enforcement.
  - Include freshness awareness using `RELAYMD_HEARTBEAT_STALE_SECONDS` (default 120) in lock diagnostics.
  - Continue requiring `--force` for takeover when another host is marked active.
- Add `relaymd-service-status` command:
  - Reports status file fields + heartbeat freshness + local tmux/port checks.
  - Exit code `0` only when orchestrator/proxy are both healthy on expected host.

5. **Address other discussed concerns (docs + operator UX)**
- Update HPC docs with:
  - new auto-pull examples (`latest` mode),
  - clear note that login-node services are non-durable and may be culled/restarted,
  - operational checks (`relaymd-service-status`, tmux/port checks),
  - log file locations and stale-heartbeat interpretation.
- Update env example with new optional knobs:
  - `RELAYMD_GHCR_OWNER`
  - `RELAYMD_HEARTBEAT_INTERVAL_SECONDS`
  - `RELAYMD_HEARTBEAT_STALE_SECONDS`
  - `STARTUP_GRACE_SECONDS`

#### Test Plan
1. **Script validation**
- `bash -n` for all updated/new wrappers.
- Shellcheck-style pass for quoting and safe eval/printf usage.

2. **Auto-tag resolution scenarios**
- explicit URIs path still works unchanged.
- `latest` mode resolves shared tag correctly.
- failure cases:
  - missing `gh`/`jq`,
  - auth scope missing,
  - no shared `sha-*` tags.

3. **Runtime reliability scenarios**
- Successful start updates active flags and heartbeat timestamps.
- Forced crash path writes non-zero exit metadata and log trail.
- Early startup failure prints immediate diagnostics and log tail.
- `relaymd-service-status` detects:
  - healthy,
  - down,
  - stale heartbeat,
  - stale lock on other host.

4. **Cross-host lock behavior**
- start on pinned host succeeds.
- start on different host is refused.
- `--force` takeover works and updates host ownership fields.

#### Assumptions and Defaults
- Keep tmux frontend deployment model in this scope (no Slurm-service migration now).
- Use “detect + log only” reliability policy (no auto-restart loops).
- Use latest shared SHA policy for GHCR auto resolution.
- Default branch name: `hpc-service-reliability`.
