# RAG-RESUME-01 — Make extended RAG checkpoint recovery unambiguous

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Order:** 2  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `fix/rag-extended-resume-stages`  
**Depends on:** `BRAIN-01`

## Goal
Ensure an extended turn resumed after a crash continues from the exact durable milestone and never skips Pass2 or global ranking.

## Primary scope
- `backend/rag/app/services/conversation_graph.py`
- `conversation checkpoint/state types`
- `conversation persistence`
- `RAG recovery tests`

## Required behavior
- Introduce explicit stages for Pass1, Pass2, final/global ranking, generation and later milestones.
- Use one authoritative stage/order model for fresh execution and resume.
- Resume after Pass1 must still execute Pass2 decision and final ranking.
- Resume after Pass2 must execute final ranking exactly once.
- Resume after final ranking must not repeat retrieval.
- Preserve regular-mode behavior, RAG-01 ranking and RAG-02 bounded concurrency.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Extract checkpoint-stage policy from conversation_graph.py if that removes stale duplicate ordering logic.

## Non-goals
- No context-assembler, hybrid, reranker, or model changes.

## Validation
- Focused checkpoint/resume tests including crash after Pass1/Pass2/final rank
- Full RAG suite
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
