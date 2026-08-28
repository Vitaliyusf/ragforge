# RAG-03 — Token-aware diverse context assembler

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Order:** 4  
**Phase:** 1 Current hardening  
**Priority:** P0  
**Branch:** `feat/rag-context-assembler`  
**Depends on:** `RAG-RESUME-01`, `CONFIG-01`

## Goal
Select final evidence with an explicit token budget, deterministic dedupe and controlled diversity instead of blindly taking first K.

## Primary scope
- `backend/rag/app/services/conversation_graph.py`
- `new domain-owned context assembler`
- `RAG config/tests`
- `citation/evaluation passage ordering`

## Required behavior
- Compute explicit evidence token budget after output/system/question/history/memory reserves.
- Never exceed the evidence budget.
- Deduplicate redundant chunks/content deterministically.
- Improve source/section diversity only when candidates are reasonably comparable.
- Never drop a clearly superior chunk merely for diversity.
- Generation and evaluation receive the exact same ordered passage list.
- Preserve citation numbering and Regular/Extended behavior.
- Do not change retrieval, Pass2, hybrid or reranker behavior.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Move the changed context-selection/prompt-evidence packing concern out of conversation_graph.py rather than leave inline and extracted versions.

## Non-goals
- No new chunker, hybrid retrieval, learned reranker, or unrelated graph refactor.

## Validation
- Focused context/citation tests
- Full RAG suite
- Ruff
- mypy only for touched typed contracts
- git diff --check

## Measurement
- Evidence tokens, source diversity, citation/answer quality when later benchmarked, E2E latency.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
