# CHUNK-02 — Contextual chunk augmentation

**Order:** 27  
**Phase:** 3 Document Representation V2  
**Priority:** P1  
**Branch:** `feat/contextual-chunk-metadata`  
**Depends on:** `CHUNK-01`

## Goal
Improve chunk representation with deterministic local document context before considering LLM-generated context.

## Primary scope
- `chunk embedding representation`
- `metadata/provenance`
- `tests/eval`

## Required behavior
- Add deterministic header from title/type/heading path/section/page when available.
- Keep raw chunk text separately for citations/UI.
- Version embedding representation independently from raw content.
- Measure deterministic context first.
- LLM contextualizer, if any, is a later isolated candidate.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Keep contextualization in one transformation module, not duplicated in parser/chunker/vector code.

## Non-goals
- No unrelated embedding model change.

## Validation
- Representation tests
- Retrieval benchmark
- Smoke30 only if promoted

## Measurement
- Retrieval metrics, embedding input tokens, ingestion latency.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
