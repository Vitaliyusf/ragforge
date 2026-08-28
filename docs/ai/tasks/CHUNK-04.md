# CHUNK-04 — Agent-assisted document repair for low-confidence cases

**Order:** 29  
**Phase:** 3 Document Representation V2  
**Priority:** P3  
**Branch:** `feat/agentic-document-repair`  
**Depends on:** `DOCPIPE-02`, `CHUNK-03`

## Goal
Use an LLM/agent only as an exception path for malformed or low-confidence document structure, not for normal chunking.

## Primary scope
- `document confidence/warnings`
- `repair agent/prompt`
- `review/audit`
- `malformed fixtures`

## Required behavior
- Trigger only from explicit parser confidence/warning policy.
- Agent outputs typed bounded repair proposal.
- Validate repaired structure deterministically.
- Record model/prompt/schema provenance.
- Use human review for destructive/ambiguous repair.
- Normal documents make zero agent calls.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** One narrow repair capability only.

## Non-goals
- No general document-agent framework.

## Validation
- Agent repair tests
- Malformed-doc benchmark
- Ingestion safety tests

## Measurement
- Repair trigger rate, structure quality, latency/cost, human-review rate.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
