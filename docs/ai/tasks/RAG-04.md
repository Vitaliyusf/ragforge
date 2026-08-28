# RAG-04 — Add a real learned reranker

**Order:** 31  
**Phase:** 4 Retrieval V2  
**Priority:** P1  
**Branch:** `feat/cross-encoder-reranking`  
**Depends on:** `RAG-05`

## Goal
Rerank a bounded hybrid candidate set with a real multilingual query-passage model before context selection.

## Primary scope
- `reranker adapter/service ownership`
- `RAG candidate pipeline`
- `metrics/eval`
- `model runtime/deps`

## Required behavior
- Start with a multilingual candidate such as BGE reranker v2 m3 or measured equivalent.
- Rerank only a bounded candidate pool.
- Preserve retrieval lineage/scores alongside reranker score.
- Timeout/fallback is explicit/deterministic.
- Clean misleading old reranker naming.
- Record reranker model/version in provenance.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Use this task to replace misleading sort/dedupe 'reranker' naming rather than keeping old and new semantics.

## Non-goals
- No widening of unrelated retrieval stages.

## Validation
- Focused reranker tests
- RAG/Vector affected suites
- Retrieval benchmark
- Smoke30

## Measurement
- Hit@1, MRR, nDCG, rerank latency, candidate count.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
