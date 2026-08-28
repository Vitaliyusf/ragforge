# DOCPIPE-02 — Add structured parser adapters and fallback policy

**Order:** 25  
**Phase:** 3 Document Representation V2  
**Priority:** P1  
**Branch:** `feat/document-parser-adapters`  
**Depends on:** `DOCPIPE-01`

## Goal
Evaluate and integrate rich parsers behind the canonical document contract without coupling the platform to one library.

## Primary scope
- `document parser adapter`
- `Docling candidate`
- `Unstructured fallback candidate`
- `existing native extractors`
- `parser tests`

## Required behavior
- Keep RAGForge ExtractedDocument as the downstream contract.
- Evaluate Docling for structured parsing.
- Evaluate Unstructured for OCR/layout/table-heavy fallback where it adds value.
- Keep simple native parsers for straightforward formats if useful.
- Record parser/version/confidence/warnings.
- Choose parser deterministically by format/capability, not an LLM agent.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Delete legacy extraction adapters made redundant by accepted parser policy.

## Non-goals
- No downstream imports of third-party parser domain objects.

## Validation
- Representative parser fixture suite
- Ingestion smoke
- Dependency/image build

## Measurement
- Structure accuracy, table/page/heading retention, latency, failure rate.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
