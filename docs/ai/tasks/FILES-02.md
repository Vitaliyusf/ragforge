# FILES-02 — Simplify Files ingestion into an explicit state machine

**Order:** 15  
**Phase:** 2 Simplification  
**Priority:** P1  
**Branch:** `refactor/files-ingestion-state-machine`  
**Depends on:** `VALIDATE-01`, `FILES-01`

## Goal
Make Files ingestion control flow explicit and remove graph abstractions that do not execute the real workflow.

## Primary scope
- `backend/files/app/services/file_ingestion_graph.py`
- `_file_ingestion.py`
- `_file_review.py`
- `state/constants/tests`
- `Files dependencies`

## Required behavior
- Represent ingestion states/transitions explicitly.
- Remove unused/dummy LangGraph construction after reference proof.
- Preserve review pause/resume, audit and rerun semantics.
- Keep transition functions small/domain-named.
- Do not replace deterministic orchestration with an LLM agent.
- Remove Files LangGraph dependency if no remaining use.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorbs the Files portion of old orchestration refactor.

## Non-goals
- No structured-document format change yet.

## Validation
- Focused ingestion/review tests
- Full Files suite
- Ingestion smoke
- Ruff
- git diff --check

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
