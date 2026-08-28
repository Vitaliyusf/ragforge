# CHUNK-01 — Structure-aware token-budgeted chunking baseline

**Order:** 26  
**Phase:** 3 Document Representation V2  
**Priority:** P0  
**Branch:** `feat/structured-token-chunking`  
**Depends on:** `DOCPIPE-01`, `VECTOR-01`

## Goal
Replace fixed 1200-character canonical chunking with deterministic structure-aware token packing while preserving source provenance.

## Primary scope
- `document blocks`
- `Files chunk creation`
- `chunk schema/version`
- `embedding jobs`
- `tests`

## Required behavior
- Chunk by structural blocks/headings/paragraphs first.
- Pack by tokenizer token target/max/overlap.
- Preserve page, section/heading path, offsets and chunk version.
- Handle oversized blocks deterministically.
- Generate deterministic chunk IDs from source/version/boundaries.
- No LLM call in baseline.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Remove old canonical fixed-character chunker only after candidate acceptance; do not keep permanent dual defaults.

## Non-goals
- No semantic/agentic chunking in this task.

## Validation
- Property tests for boundaries/offsets
- Ingestion tests
- Retrieval benchmark versus Baseline V1

## Measurement
- MRR, Recall@5/20, Hit@1, nDCG, chunks/doc, tokens/chunk, index size, ingestion latency.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
