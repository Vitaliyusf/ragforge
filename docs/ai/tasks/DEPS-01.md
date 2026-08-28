# DEPS-01 — Staged dependency and image-surface modernization

**Order:** 12  
**Phase:** 1 Current hardening  
**Priority:** P1  
**Branch:** `chore/staged-dependency-modernization`  
**Depends on:** `SHARED-02`, `SEC-03`

## Goal
Modernize dependencies in coherent batches and remove dependencies for runtime paths that no longer exist.

## Primary scope
- `docker/requirements-base.txt`
- `service requirements`
- `frontend/package.json`
- `Dockerfiles`
- `dependency audits`

## Required behavior
- Remove unused dependencies before upgrading.
- Clarify common-runtime vs service-specific ownership.
- Upgrade one risk family at a time.
- Remove Torch/Transformers/Accelerate from llm_agent if local HF provider is retired.
- Remove Chroma/LangChain dependencies for inactive adapters.
- Keep audits and severity policy explicit.
- Avoid mass upgrade.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Delete obsolete provider/adapter code in the same batch when dependency removal proves it dead.

## Non-goals
- No single mass dependency upgrade.

## Validation
- Affected service suite per batch
- Frontend tests/build for npm batch
- Image build when requirements change
- Dependency audits

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
