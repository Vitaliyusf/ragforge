# AGENT-01 — Harden Memory agent server-side mutation policy

**Order:** 39  
**Phase:** 5 Memory V2  
**Priority:** P1  
**Branch:** `feat/memory-agent-policy`  
**Depends on:** `MEM-03`, `LLM-CTRL-01`

## Goal
Ensure the existing Memory Agent cannot bypass canonical write policy, auth, audit or destructive-operation controls.

## Primary scope
- `memory agent tools`
- `LongTermMemoryService policy`
- `auth/audit`
- `tests`

## Required behavior
- All mutations pass server-side ownership/write policy.
- Destructive operations use explicit bounded authorization.
- Untrusted text cannot redefine tool permissions.
- Record tool outcome without hidden reasoning.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Keep tools thin over canonical services; remove duplicated mutation logic.

## Non-goals
- No general agent mode.

## Validation
- Adversarial agent policy tests
- Memory suite

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
