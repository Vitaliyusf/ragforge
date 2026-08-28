# BRAIN-FIX-01 — Make repo-brain deterministic, current, and cache-safe

**Branch:** `fix/repo-brain-source-authority`  
**Priority:** P0 maintenance / correctness  
**Goal:** Remove stale runtime guidance and make repo-brain indexing immune to task-local caches, generated output, and historical instruction drift.

## Why this task exists

Three independent problems are interacting:

1. Old task/template/history artifacts can still contain generic runtime guidance such as Python 3.11.
2. Current repository runtime is Python 3.12, but repo-brain retrieval does not have a sufficiently explicit source-authority model.
3. `rebuild_repo_brain.py` previously excluded only exact directory names such as `.uv-cache`; task-local variants such as `.uv-cache-safe01-memory` and `.uv-python-safe01-memory` can still enter the filesystem walk and explode rebuild cost.

This task fixes the mechanism, not one task.

---

# 1. Source-of-truth hierarchy

Create one canonical current runtime/tooling document:

`docs/ai/RUNTIME_CONTRACT.md`

Minimum contract:

```text
Canonical Python: 3.12, derived from .python-version
Canonical Node: 24 LTS
Canonical test dependency layer:
  docker/requirements-base.txt
  backend/<service>/requirements.txt
  backend/requirements-test.txt

Canonical local fallback:
  uv run --isolated --python 3.12 ...

Canonical authoritative mypy scope:
  mypy backend/shared backend/gateway/app --config-file mypy.ini

Canonical Ruff:
  repository-pinned Ruff version

Local environment:
  never repair .venv during a task
  Windows uv setup failure → one corrected retry
  if still blocked and a compatible Linux container exists, use the container
```

Also define:

> Runtime/tooling facts in `RUNTIME_CONTRACT.md`, `.python-version`, and CI config override generic runtime text embedded in older task specs, handoffs, historical docs, or benchmark records unless the active task explicitly owns a runtime/toolchain migration.

Update current authoritative docs to reference this contract rather than hardcoding a Python version in several places.

At minimum inspect:
- `AGENTS.md`
- `docs/ai/ENGINEERING_RULES.md`
- `docs/ai/TASK_TEMPLATE.md`
- `docs/ai/TESTING.md`
- `docs/ai/TESTING_OPTIMIZED.md`
- `docs/ai/WORKFLOW.md`
- `docs/ai/memory/GOTCHAS.md`

Do NOT rewrite benchmark artifacts or historical handoff truth.

---

# 2. Active task specs must not freeze generic runtime versions

Audit `docs/ai/tasks/*.md`.

Classify task files:
- active / future
- completed / historical
- runtime/toolchain migration task

For active/future tasks that contain generic statements such as:

```text
Python target is 3.11
Use isolated Python 3.11
CI uses Python 3.11
```

replace the generic runtime assumption with:

```text
Use the canonical runtime/tooling from docs/ai/RUNTIME_CONTRACT.md.
```

Exception:
- a task whose explicit purpose is a Python/runtime/toolchain migration may name the versions it owns.

Do NOT falsify historical completed task evidence.

If completed task specs remain in `docs/ai/tasks/`, either:
- mark them clearly as completed/historical in metadata/frontmatter, or
- move them to an archive location if the existing repo conventions support that safely.

Do not mass-rewrite historical content.

---

# 3. Fix repo-brain file enumeration at the root

Do NOT continue maintaining an ever-growing exact-name directory blacklist as the primary mechanism.

Preferred implementation in `scripts/ai/rebuild_repo_brain.py`:

Use Git to enumerate repository source:

```text
git ls-files --cached --others --exclude-standard -z
```

This provides:
- tracked files
- current untracked source files
- excludes Git-ignored caches/temp files automatically
- no recursive traversal through node_modules/venvs/uv caches

Then apply a small explicit safety filter.

Always exclude derived/private trees even if accidentally tracked/unignored:

```text
.agent-private/
docs/ai/generated/
.git/
```

Also exclude binary/unsupported extensions and enforce an existing/reasonable max-file-size guard.

Important:
- include untracked production source so the brain can represent an uncommitted task worktree;
- exclude deleted files;
- do not rely solely on `Path.rglob()` / `os.walk()` over the entire workspace.

If Git enumeration is unavailable, the fallback filesystem walker must have robust pattern-based exclusions, not only exact names.

Fallback directory exclusion must reject at least:

```text
.uv-cache
.uv-cache-*
.uv-python
.uv-python-*
.venv
venv
node_modules
.next
__pycache__
.pytest_cache
.ruff_cache
.mypy_cache
.agent-private
docs/ai/generated
coverage
dist
build
```

Use prefix/glob/path rules.

---

# 4. Fix `.gitignore` cache patterns

Audit `.gitignore`.

Ensure task-local tooling cannot appear as normal untracked repository source.

Required patterns should cover variants, not only one exact folder:

```gitignore
.agent-private/
.uv-cache*/
.uv-python*/
.ruff_cache/
.pytest_cache/
.mypy_cache/
.venv/
```

Preserve any broader correct existing rules.

Do not ignore legitimate source directories.

---

# 5. Tool cache policy

Add a single rule to current workflow/runtime docs:

> All workspace-local task/tool caches belong under `.agent-private/tooling/<task-id>/` when possible.

Recommended:

```text
.agent-private/
  tooling/
    SAFE-01/
      uv-cache/
      uv-python/
      ruff-cache/
      pytest-tmp/
```

Do not create task-local directories at repository root such as:

```text
.uv-cache-safe01
.uv-python-safe01-memory
```

For read-only Linux container validation:

```text
RUFF_CACHE_DIR=/tmp/ruff-cache
pytest temp → /tmp
```

Do not make the repository writable solely for tool caches.

---

# 6. Repo-brain authority metadata

Update the generated index schema minimally so entries can be classified.

Recommended bounded `source_class`:

```text
authoritative
task
history
source
```

Suggested authority:

```text
authoritative:
  AGENTS.md
  .python-version
  docs/ai/RUNTIME_CONTRACT.md
  docs/ai/ENGINEERING_RULES.md
  docs/ai/TESTING.md
  docs/ai/TESTING_OPTIMIZED.md
  docs/ai/WORKFLOW.md

task:
  docs/ai/tasks/**

history:
  docs/ai/memory/HISTORY.md
  docs/ai/memory/handoffs/**
  archived task/run docs
```

`docs/ai/generated/**` should not be indexed at all.

Do not build a complex knowledge-management framework.

---

# 7. Fix `brain_query.py` precedence

Generic queries about:
- Python/runtime
- validation
- testing
- tooling
- environment fallback
- CI authority

must prefer current authoritative sources over task/history documents.

Do not simply delete historical evidence.

Preferred approach:
- add a bounded ranking boost for `source_class=authoritative`;
- demote `history`;
- exclude `generated`;
- keep direct task-ID matches useful for task-specific behavior.

Exact task file still matters for task-owned semantics.

But generic environment/runtime guidance from a task file must never override the canonical runtime contract unless the task explicitly owns runtime/toolchain migration.

---

# 8. Add regression tests

Add focused tests for repo-brain/tooling behavior.

## File enumeration

Given a temporary Git repository, prove included:

```text
tracked source file
untracked nonignored source file
```

Prove excluded:

```text
.agent-private/
.uv-cache/
.uv-cache-safe01/
.uv-cache-safe01-memory/
.uv-python-safe01/
.uv-python-safe01-memory/
.venv/
node_modules/
.next/
__pycache__/
.ruff_cache/
.pytest_cache/
.mypy_cache/
docs/ai/generated/
```

## Gitignore behavior

Prove task-local cache variants are ignored.

## Authority

Construct indexed fixtures containing:

```text
authoritative runtime: Python 3.12
historical task runtime: Python 3.11
```

A generic query such as:

```text
canonical Python validation runtime
```

must rank the authoritative 3.12 source above historical/task 3.11 text.

## Task specificity

A direct task query must still retrieve the relevant task spec.

---

# 9. Add a brain self-check

Extend `validate_ai_memory.py` or add a small bounded validation that fails if the generated index contains paths under forbidden runtime/cache/generated prefixes.

Examples:

```text
forbidden indexed path:
.uv-cache-safe01/...
.uv-python-safe01-memory/...
.agent-private/...
docs/ai/generated/...
```

Also validate that the canonical runtime contract agrees with `.python-version`.

Do not parse every historical task file and fail because history mentions an old runtime.

---

# 10. Final sequence

Before final rebuild:

- source frozen;
- all task-local root caches removed or ignored;
- generated output excluded from input enumeration.

Final sequence:

```text
focused brain tests
→ repo-brain self-check
→ git diff --check
→ NO MORE SOURCE EDITS
→ record handoff once
→ rebuild brain once
→ validate brain once
```

Do not run the rebuild repeatedly while debugging.

---

# 11. Scope

Expected touched files:

```text
.gitignore
AGENTS.md
docs/ai/RUNTIME_CONTRACT.md
docs/ai/TASK_TEMPLATE.md
docs/ai/ENGINEERING_RULES.md
docs/ai/TESTING.md
docs/ai/TESTING_OPTIMIZED.md
docs/ai/WORKFLOW.md
docs/ai/memory/GOTCHAS.md
scripts/ai/rebuild_repo_brain.py
scripts/ai/brain_query.py
scripts/ai/validate_ai_memory.py
focused tests for scripts/ai
active/future task specs only where stale generic runtime text exists
```

Do not touch application business logic.

---

# 12. Validation runtime

Use canonical Python 3.12 only.

Do not use Python 3.11 for this task.

Do not repair `.venv`.

If Windows uv is blocked:
- one corrected retry maximum;
- then use an existing compatible Linux Python 3.12 container.

All cache/temp state must be outside the brain input set.

---

# 13. Completion report

Report:

```text
root causes found:
stale active task specs:
historical files intentionally retained:
canonical runtime authority:
brain enumeration method:
cache patterns:
generated/private exclusion:
brain query precedence:
tests:
final indexed file count:
forbidden indexed paths:
brain validation:
```

Also report exact files changed.

No commit/push unless explicitly requested.

STOP after this task. Do not start FILES-01.
