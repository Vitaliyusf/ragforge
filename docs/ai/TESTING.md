# RAGForge Testing Policy — CI-Delegated / Low-Token

## Principle

```text
Test what changed.
Do not make the coding agent re-run the whole CI pipeline.
```

The agent owns fast, relevant validation.
GitHub CI owns broad clean-environment validation.

## Level 0 — NO-OP audit

When current code already satisfies a task:

Run only acceptance-focused tests.

Example:

```text
BMARK-05 already implemented
→ hash/version tests
→ stale-label test
→ historical-run test
→ done
```

Do not run:
- full RAG suite;
- full gateway suite;
- full frontend suite;
- production build;
- repo-wide Ruff;
- full mypy;
- memory rebuild unless memory actually changed.

Expected final status:

```text
NO-OP VERIFIED
```

## Level 1 — Focused implementation tests

Use while coding.

```bash
python scripts/ai/check.py focused rag \
  --files backend/rag/app/services/eval_runner.py \
          backend/rag/app/services/eval_store.py \
  --tests app/tests/test_eval_runner.py \
          app/tests/test_eval_store.py
```

This runs:
- Ruff on changed Python files;
- only the named test files.

Add mypy only if justified:

```bash
... --mypy
```

Do not rerun a PASS unless later edits can invalidate it.

## Level 2 — Affected service

Use once near completion only for cross-cutting/high-risk service changes.

```bash
python scripts/ai/check.py affected rag
```

Examples that justify this:
- new RPC/action;
- repository/storage changes;
- tenant/security boundary;
- runner lifecycle/concurrency;
- broad service contract.

Examples that usually do not:
- small pure helper;
- local parser change;
- text/UI-only change;
- no-op audit.

## Level 3 — Full

Rare locally.

```bash
python scripts/ai/check.py full --fail-fast
```

Use only for:
- explicit CI-equivalent local validation;
- broad shared infrastructure/contracts;
- runtime/dependency/CI changes;
- release verification.

## Environment doctor

Run once per task before the first Python validation:

```bash
python scripts/ai/check.py doctor
```

Do not repeatedly probe:
- `.venv`;
- `py`;
- `python3`;
- `uv`;
- pytest plugin combinations.

If the environment cannot collect tests normally:

```text
BLOCKED
```

Do not disable plugin autoload and call the suite green.

## Ruff

Normal task:

```text
changed files only
```

Do not run `ruff check backend/` locally just to validate an unrelated feature.
Repo-wide lint belongs to CI unless lint cleanup is the task.

## Mypy

Run only when:
- typed contracts changed;
- schema/config/Pydantic models changed;
- touched code is in the normal mypy scope;
- task acceptance requires it.

Do not repeatedly shrink the scope to get a green result.

## Frontend

During coding:

```bash
npm test -- <specific-test-file>
```

Do not run full frontend tests locally by default.

Run:

```bash
npm run build
```

only for production-impacting/cross-cutting frontend changes.

## Pytest integrity

Authoritative validation must not use:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`;
- broad `-k "not ..."` exclusions;
- hidden collection errors;
- skipped failing async coverage.

Diagnostic runs may investigate an environment issue, but must be reported as diagnostic only.

## Output

PASS:

```text
Ruff: PASS
Pytest focused: PASS
Overall: PASS
```

BLOCKED:

```text
Pytest: BLOCKED
<first actionable environment error>
Overall: BLOCKED
```

FAIL:
- show only relevant failure tail;
- stop after first useful failure during implementation.

## Recommended task flow

```text
read task
→ audit current implementation
→ NO-OP? acceptance tests only → done

otherwise:
targeted implementation
→ focused tests
→ focused tests again only if later edits invalidate them
→ optional affected-service suite once
→ final diff
→ memory once
→ PR
→ GitHub CI broad validation
```
