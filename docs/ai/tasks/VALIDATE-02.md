# VALIDATE-02 — Advanced platform release gate

**Order:** 54  
**Phase:** 8 Final release  
**Priority:** P0  
**Branch:** `release/advanced-validation-v2`  
**Depends on:** `DEPLOY-01`, `CHAOS-01`, `OBS-02`

## Goal
Validate the simplified, structured-document, Retrieval V2 and Memory V2 platform as one release candidate and establish Baseline V2.

## Primary scope
- `CI`
- `E2E`
- `security/supply chain`
- `chaos`
- `chat/ingestion`
- `quality benchmarks`
- `runtime provenance`

## Required behavior
- Run clean CI and browser E2E.
- Validate production profile/readiness.
- Run representative structured-document ingestion.
- Run current smoke/full/retrieval quality suites on promoted index/config.
- Run memory quality and relevant agent suite.
- Run selected chaos checks.
- Archive Baseline V2 with full provenance.
- No code changes inside validation.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** No refactoring; validation only.

## Non-goals
- No implementation work.

## Validation
- All required gates pass or explicit blocker tasks are created
- Baseline V2 is reproducible and documented

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
