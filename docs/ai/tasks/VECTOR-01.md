# VECTOR-01 — Versioned vector index lifecycle

**Order:** 23  
**Phase:** 3 Document Representation V2  
**Priority:** P0  
**Branch:** `feat/vector-index-lifecycle`  
**Depends on:** `VALIDATE-01`

## Goal
Support safe side-by-side index versions, rebuilds, validation and atomic promotion for chunk/embedding changes.

## Primary scope
- `Vector service/Qdrant implementation`
- `index metadata/aliases`
- `ingestion write target`
- `RAG read target`
- `migration tests`

## Required behavior
- Define index version identity from chunking/embedding representation.
- Build candidate collection/version without overwriting active.
- Validate candidate completeness/metadata.
- Promote atomically via alias/config.
- Keep bounded rollback window and explicit retirement.
- Make derived index rebuildable from canonical state.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Remove fake vector-backend pluggability/legacy envelopes that obstruct clear Qdrant version ownership.

## Non-goals
- No hybrid/reranker yet.

## Validation
- Vector suite
- Index lifecycle integration tests
- Qdrant smoke

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use direct `uv run --isolated --python 3.11`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
