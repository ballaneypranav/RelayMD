# Enforcement Plan: Ruff + Pylint Code Quality Rules

## Current State

| Item | Status |
|---|---|
| **Pre-commit framework** | Not installed — repo uses a custom `.githooks/pre-commit` shell script |
| **Ruff rules today** | `E, F, I, UP, B, SIM` — no complexity / pylint rules yet |
| **pre-commit-hooks repo** | No `.pre-commit-config.yaml` exists |
| **Pylint** | Not a dependency |

### Existing Violations (against your proposed rules)

Running `ruff check --select C90,PL` across `src/` and `packages/` (excluding the generated API client) finds **112 violations**:

| Rule | Count | Description |
|---|---|---|
| `PLR2004` | 20 | Magic value comparisons |
| `PLC0415` | 18 | Import outside top-level |
| `PLW0603` | 18 | Global statement |
| `PLR0913` | 17 | Too many arguments (>5) |
| `C901` | 14 | Too complex (cyclomatic) |
| `PLR0912` | 11 | Too many branches |
| `PLR0915` | 6 | Too many statements |
| `PLR0911` | 5 | Too many return statements |
| `PLC0207` | 2 | Missing maxsplit arg |
| `PLR1711` | 1 | Useless return |

### Files Exceeding 400 Lines

| File | Lines |
|---|---|
| `packages/relaymd-worker/src/relaymd/worker/main.py` | 1445 |
| `src/relaymd/orchestrator/services/slurm_provisioning_service.py` | 650 |
| `packages/relaymd-worker/src/relaymd/worker/bootstrap.py` | 593 |
| `src/relaymd/orchestrator/services/worker_lifecycle_service.py` | 460 |
| `src/relaymd/orchestrator/main.py` | 445 |
| `src/relaymd/orchestrator/routers/jobs_operator.py` | 435 |
| `src/relaymd/orchestrator/config.py` | 431 |
| `src/relaymd/cli/commands/service.py` | 421 |

> [!IMPORTANT]
> 8 source files already exceed 400 lines, and the worker `main.py` is **1445 lines**.
> Fixing all of these up-front would be that "massive PR" we want to avoid.

---

## Proposed Approach: Gradual Ratchet

The key insight is: **pre-commit (and ruff) only run on staged/changed files by default**, so new code is held to the standard immediately, while legacy violations are exempt until someone touches those files.

### Phase 1 — This PR (Config Only)

This PR adds the rules and tooling **without fixing any existing code**:

1. **Add `C90` and `PL` to the ruff `select` list** in `pyproject.toml`, along with the `max-complexity`, `max-args`, and `max-statements` thresholds.

2. **Baseline existing violations with per-file `noqa` comments** — **NO.** This is noisy. Instead, use **ruff's `per-file-ignores`** to exempt the 8 files that currently violate the module-length rule, and the specific rules they violate. This is a tiny, auditable config block.

3. **For the `max-module-lines = 400` rule**: Ruff doesn't natively enforce max file length. Options:
   - **(A) Skip pylint entirely** — Use ruff's `PL` rules for everything *except* file length, and add a lightweight shell check in the hook for file length on staged files only.
   - **(B) Add pylint as a full pre-commit hook** — Heavy, slow, and requires pylint as a dependency. Not recommended for this repo.
   - **→ Recommended: Option A.** A 3-line shell snippet in the existing `.githooks/pre-commit` checks `wc -l` on staged `.py` files. Fast, zero new dependencies.

4. **Wire the new ruff rules into `.githooks/pre-commit`** — The existing hook already runs `ruff check --fix .` on the whole repo. Change it to only check **staged files** (matching the pyright behavior). This way existing violations in untouched files don't block commits.

5. **No `.pre-commit-config.yaml` / `pre-commit` framework** — The repo already has a working `.githooks` workflow with `make setup-hooks`. Adding a second hook framework introduces friction. We'll keep the existing pattern and extend it.

### Phase 2 — Ongoing (Organic Cleanup)

- Every time a developer touches a legacy file, ruff will flag violations *in that file*, and the commit hook blocks until they're fixed.
- The `per-file-ignores` list in `pyproject.toml` serves as a visible "tech debt backlog" — teams can chip away at it in small PRs.
- Optionally, create a tracking Linear issue per exempt file.

---

## Concrete Changes in This PR

### 1. `pyproject.toml` — Ruff Config

```diff
 [tool.ruff.lint]
-select = ["E", "F", "I", "UP", "B", "SIM"]
+select = ["E", "F", "I", "UP", "B", "SIM", "C90", "PL"]

+[tool.ruff.lint.mccabe]
+max-complexity = 10
+
+[tool.ruff.lint.pylint]
+max-args = 5
+max-statements = 50
+
+[tool.ruff.lint.per-file-ignores]
+# --- Legacy exemptions (gradual ratchet) ---
+# Remove each entry as the file is refactored below thresholds.
+"packages/relaymd-worker/src/relaymd/worker/main.py" = ["C901", "PLR0912", "PLR0913", "PLR0915", "PLR2004", "PLC0415", "PLW0603"]
+"packages/relaymd-worker/src/relaymd/worker/bootstrap.py" = ["C901", "PLR0912", "PLR0913", "PLR0915", "PLR2004", "PLC0415", "PLW0603"]
+"src/relaymd/orchestrator/services/slurm_provisioning_service.py" = ["C901", "PLR0912", "PLR0913", "PLR0915", "PLR2004", "PLC0415"]
+# ... (exact list determined by running ruff against each file)
```

### 2. `.githooks/pre-commit` — Scoped to Staged Files + File Length Check

```bash
# Only check staged Python files (not entire repo)
mapfile -t staged_py < <(git diff --cached --name-only --diff-filter=ACMR | grep '\.py$' || true)
if [[ ${#staged_py[@]} -gt 0 ]]; then
  uv run ruff check --fix "${staged_py[@]}"
  uv run ruff format "${staged_py[@]}"
  uv run pyright "${staged_py[@]}"

  # Enforce max 400 lines per file
  for f in "${staged_py[@]}"; do
    lines=$(wc -l < "$f")
    if [[ $lines -gt 400 ]]; then
      echo "pre-commit: $f has $lines lines (max 400). Refactor before committing."
      exit 1
    fi
  done
fi
```

### 3. NOT Adding

- ❌ `.pre-commit-config.yaml` — would conflict with existing `.githooks` workflow
- ❌ `pylint` as a dependency — ruff covers the same `PL*` rules natively
- ❌ Bulk code rewrites — violations in untouched files are exempt

---

## Decision Points for You

1. **File-length enforcement on legacy files** — The 8 files above 400 lines would fail the `wc -l` check if anyone touches them. Two options:
   - **(A) Exempt the 8 files from the length check too** (whitelist in the hook), requiring explicit refactoring PRs later.
   - **(B) Enforce immediately** — anyone touching those files must split them first. This is stricter but may slow down unrelated work.
   - **Recommendation: (A)** — whitelist + a tracking issue per file.

2. **`PLR2004` (magic values)** — 20 violations. This rule can be noisy for things like HTTP status codes (`if resp.status == 200`). Do you want to:
   - **(A) Include it** in the enforced set (with per-file exemptions for legacy)?
   - **(B) Exclude it** entirely as too noisy?

3. **`PLC0415` (import outside top-level)** and **`PLW0603` (global statement)** — 18 violations each. These are often intentional patterns (lazy imports, module-level singletons). Same question: enforce or exclude?

> [!TIP]
> Let me know your choices on these 3 points and I'll implement the changes on a new branch.
