# CHAOS-01 — Controlled failure and recovery suite

**Order:** 51  
**Phase:** 7 Distributed production  
**Priority:** P2  
**Branch:** `test/chaos-recovery`  
**Depends on:** `DIST-01`, `DIST-02`, `HEALTH-01`

## Goal
Prove recovery behavior under realistic dependency and process failures.

## Primary scope
- `integration harness`
- `RAG/Files/Memory/Vector/Kafka/Rabbit/Mongo/vLLM scenarios`

## Required behavior
- Kill/restart RAG after Pass1/Pass2.
- Drop Qdrant during memory/index write and verify repair.
- Inject Kafka duplicates/restart consumers.
- Drop RabbitMQ during bounded RPC.
- Drop Mongo and verify readiness/error semantics.
- Disconnect browser during completion.
- Keep tests deterministic and isolated.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Non-trivial defects become separate targeted fixes rather than broad changes inside the chaos task.

## Non-goals
- No production chaos.

## Validation
- Controlled chaos suite with expected converged state per scenario

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
