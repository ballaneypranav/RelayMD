# Enforcement Plan: Ruff + Pylint Code Quality Rules

## Branch: `chore/enforce-ruff-pl-rules`

### What Has Landed

| Commit | Description |
|---|---|
| `a76fa22` | Add C90/PL ruff rules + gradual-ratchet per-file-ignores baseline |
| `b1ee3f7` | Refactor `axiom_logging.py` — eliminate globals and lazy imports (drops PLW0603/PLC0415) |
| `b553878` | Bump version to 0.2.1 |
| *(this PR)* | **Audit and prune stale per-file-ignores** — remove 26 source-file entries that had 0 real violations; add precise test-file exemptions |

---

## Current State

| Item | Status |
|---|---|
| **Ruff rules** | `E, F, I, UP, B, SIM, C90, PL` — enforced on staged files via `.githooks/pre-commit` |
| **max-complexity** | 10 (C901) |
| **max-args** | 5 (PLR0913) |
| **max-statements** | 50 (PLR0915) |
| **per-file-ignores** | Pruned: 26 stale source-file entries removed; 20 test-file entries added |
| **File-length check** | Shell `wc -l` in `.githooks/pre-commit`, max 400 lines, legacy files exempted |

### Remaining Source-File Exemptions (tech debt backlog)

| File | Rules Exempted | Effort to Fix |
|---|---|---|
| `worker/main.py` | C901, PLC0415, PLR0912, PLR0913, PLR0915 | High — 1445-line file |
| `orchestrator/services/slurm_provisioning_service.py` | C901, PLC0415, PLR0911, PLR0912, PLR0915, PLR2004, PLW0603 | High — 650 lines |
| `orchestrator/services/worker_lifecycle_service.py` | C901, PLR0912, PLR0915 | Medium |
| `orchestrator/main.py` | C901, PLC0207, PLR0911 | Medium |
| `orchestrator/services/job_history_service.py` | C901, PLR0912, PLR0913 | Medium |
| `orchestrator/config.py` | C901, PLC0415, PLR0915 | Medium |
| `settings_sources.py` | C901, PLR0912 | Low |
| `cli/commands/service.py` | C901, PLR0912 | Low |
| `cli/config.py` | C901, PLC0415 | Low |
| `cli/services/submit_service.py` | C901, PLR2004 | Low |
| `worker/logging.py` | PLC0415, PLW0603 | Low — lazy import pattern |
| `cli/context.py` | PLC0415, PLW0603 | Low — global singleton |
| `orchestrator/db.py` | PLW0603 | Low — module-level singletons |
| `orchestrator/logging.py` | PLC0415, PLW0603 | Low |
| `worker/bootstrap.py` | PLW0603 | Low |
| `cli/__main__.py` | PLC0415, PLR0913 | Low |
| `dashboard_proxy_main.py` | PLC0415 | Low |
| `cli/remote_dispatch.py` | PLR0911 | Low |
| `orchestrator/tailscale.py` | PLR0911 | Low |
| `worker/gateway.py` + `heartbeat.py` | PLR0913, PLR2004 | Low |
| `storage/client.py` + `core_secret_management.py` | PLR0913, PLR2004 | Low |
| `orchestrator/slurm.py` + `routers/jobs_operator.py` | PLR0913, PLR2004 | Low |
| `orchestrator/salad_scaler.py` + `services/job_transitions.py` | PLR0913 | Low |
| `worker/job_execution.py` | PLR0911, PLR0913 | Low |
| `cli/commands/jobs.py` | PLR0912 | Low |
| `cli/commands/submit.py` | PLR0913, PLR2004 | Low |
| `scripts/check_infisical_secrets.py` | PLC0415 | Low |

### Test-File Exemptions

Tests are allowed `PLR2004` (magic numbers in assertions are normal). A few also allow specific rules due to large integration-test helper classes. **No action required unless tests are refactored.**

---

## Decision Points (from original plan — resolved or open)

1. ✅ **File-length enforcement on legacy files** — Legacy files exempted in the hook via whitelist; explicit tracking issues planned.
2. ✅ **`PLR2004` (magic values)** — Included in enforced set for source; exempted in test files.
3. ✅ **`PLC0415` / `PLW0603`** — Enforced; legacy files exempted with explicit entries.

---

## Proposed Approach: Gradual Ratchet

New code is held to the standard immediately via pre-commit staged-file checks. Legacy exemptions in `pyproject.toml` serve as a visible **tech debt backlog** — teams chip away at them file by file.

### Priority Order for Removing Source-File Exemptions

1. **Low-effort PLW0603 / PLC0415 globals/lazy-imports** — Already done for `axiom_logging.py`. Next: `worker/logging.py`, `orchestrator/logging.py`, `orchestrator/db.py`, `cli/context.py`.
2. **PLR0912 / C901 complexity** — Extract sub-functions to bring cyclomatic complexity < 10.
3. **PLR0913 too-many-args** — Introduce kwargs dataclasses/models; already done for `axiom_logging.py`.
4. **High-effort files (worker/main.py, slurm_provisioning_service.py)** — Dedicated refactor PRs.

---

## Not Adding

- ❌ `.pre-commit-config.yaml` — conflicts with existing `.githooks` workflow
- ❌ `pylint` as a dependency — ruff's `PL*` rules cover the same checks natively
- ❌ Bulk code rewrites — violations in untouched files are exempt until touched
