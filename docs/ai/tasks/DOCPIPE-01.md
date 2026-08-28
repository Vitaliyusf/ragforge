# DOCPIPE-01 — Introduce a canonical structured document model

**Order:** 24  
**Phase:** 3 Document Representation V2  
**Priority:** P0  
**Branch:** `feat/structured-document-contract`  
**Depends on:** `VALIDATE-01`, `FILES-02`, `EMBED-01`

## Goal
Replace `extract(file) -> str` as the canonical internal representation with a RAGForge-owned structured document/block contract.

## Primary scope
- `Files ingestion/extraction boundary`
- `new document models`
- `existing extractors/adapters`
- `chunk persistence/tests`

## Required behavior
- Define ExtractedDocument/DocumentBlock with stable IDs, type, text, page, section/heading path, parent, offsets and extraction metadata.
- Preserve source/version provenance.
- Map existing extractors into the new contract without changing retrieval yet.
- Version the contract.
- Keep private raw source data out of logs/transports unless bounded.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Move extraction-specific logic out of Embedding into the document-ingestion domain while implementing the canonical contract.

## Non-goals
- No advanced parser library promotion yet.

## Validation
- PDF/DOCX/MD/TXT fixture tests
- Files/Embedding affected suites
- Ingestion fixture tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
