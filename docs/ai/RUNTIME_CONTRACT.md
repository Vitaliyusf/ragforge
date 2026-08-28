# Runtime & Tooling Contract

Canonical, current runtime and tooling facts for this repository.

> **Authority rule**
>
> Runtime/tooling facts in this file, `.python-version`, and `.github/workflows/`
> override generic runtime text embedded in older task specs, handoffs, historical
> docs, or benchmark records — unless the active task explicitly owns a
> runtime/toolchain migration, in which case that task owns the versions it names.

## Canonical runtime

```text
Canonical Python: 3.12, derived from .python-version
Canonical Node:   24 LTS (NODE_VERSION in .github/workflows/ci.yml, node:24-alpine)
```

CI never hardcodes a Python version: every job uses
`python-version-file: .python-version`. Service images use `python:3.12-slim`.

## Canonical test dependency layer

```text
docker/requirements-base.txt
backend/<service>/requirements.txt
backend/requirements-test.txt
```

A local result is authoritative only when it preserves that layering. Adding an
ad-hoc dependency (for example `uv run --with <missing-package>`) to turn a red
canonical lane green produces `NON-AUTHORITATIVE / ENVIRONMENT-ADJUSTED`, never
`PASS`.

## Canonical local fallback

```text
uv run --isolated --python 3.12 ...
```

## Canonical authoritative mypy scope

```bash
mypy backend/shared backend/gateway/app --config-file mypy.ini
```

File-by-file mypy is not equivalent to that scope.

## Canonical Ruff

The repository-pinned Ruff version in `backend/requirements-dev.txt`
(currently `ruff==0.4.9`). CI runs `ruff check backend/`.

## Local environment

```text
never repair .venv during a task
Windows uv setup failure → one corrected retry, then BLOCKED
if still blocked and a compatible Linux container exists, use the container
```

## Tool cache policy

All workspace-local task/tool caches belong under `.agent-private/tooling/<task-id>/`
when possible:

```text
.agent-private/
  tooling/
    SAFE-01/
      uv-cache/
      uv-python/
      ruff-cache/
      pytest-tmp/
```

Never create task-local cache directories at the repository root
(`.uv-cache-safe01`, `.uv-python-safe01-memory`, …). They pollute the working
tree, and repo-brain input enumeration must not have to chase new name variants.

For read-only Linux container validation:

```text
RUFF_CACHE_DIR=/tmp/ruff-cache
pytest temp → /tmp
```

Do not make the repository writable solely for tool caches.

## Repo-brain source authority

`scripts/ai/rebuild_repo_brain.py` classifies every indexed file:

```text
authoritative  AGENTS.md, .python-version, docs/ai/RUNTIME_CONTRACT.md,
               docs/ai/ENGINEERING_RULES.md, docs/ai/TESTING.md,
               docs/ai/TESTING_OPTIMIZED.md, docs/ai/WORKFLOW.md
task           docs/ai/tasks/**
history        docs/ai/memory/HISTORY.md, docs/ai/memory/handoffs/**,
               archived task/run docs
source         everything else
```

`scripts/ai/brain_query.py` boosts `authoritative`, demotes `history`, and never
indexes `docs/ai/generated/**` as a content source. A direct task-ID query still
retrieves that task's spec — but generic environment/runtime guidance inside a
task file never overrides this contract.
