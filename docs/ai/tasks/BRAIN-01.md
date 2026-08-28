# BRAIN-01 — Anti-monolith task and engineering guardrails

**Order:** 1  
**Phase:** 0 Governance  
**Priority:** P0  
**Branch:** `chore/ai-complexity-ratchet`  
**Depends on:** None

## Goal
Change the repository AI/task rules so future work simplifies touched hotspots instead of continuously growing monoliths, duplicate implementations, and permanent compatibility paths.

## Primary scope
- `docs/ai/ENGINEERING_RULES.md`
- `docs/ai/TASK_TEMPLATE.md`
- `docs/ai/WORKFLOW.md`
- `docs/ai/TESTING.md`
- `docs/ai/TESTING_OPTIMIZED.md`
- `docs/ai/memory/GOTCHAS.md`
- `docs/ai/memory/MEMORY_PROTOCOL.md`

## Required behavior
- Add a touched-hotspot complexity ratchet.
- Add a new-file gate requiring one clear domain responsibility.
- Forbid permanent legacy+v2 dual paths; temporary compatibility needs a removal condition/task.
- Put Local refactor budget into every task.
- Add comment policy: WHY/invariants, not syntax narration.
- Add final complexity delta to task reports.
- Document that doctor is not a universal gate and isolated uv is an accepted fallback.
- Require reference/capability search before creating a second implementation.
- Require one authoritative implementation per capability and honest configuration behavior.
- Add focused/domain test selection, an isolated compatibility lane and a ban on test-count gaming.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** This task changes the rules that govern all later local refactoring.

## Non-goals
- Do not modify production behavior or mass-refactor source.

## Validation
- Markdown/link checks
- repo-brain rebuild/validation once after edits

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
