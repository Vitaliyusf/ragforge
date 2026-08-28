# OBS-02 — SLOs, distributed observability and GPU/queue telemetry

**Order:** 47  
**Phase:** 6 Quality & Observability  
**Priority:** P2  
**Branch:** `feat/distributed-observability`  
**Depends on:** `HEALTH-01`, `OBS-TRACE-01`

## Goal
Define operational SLOs and expose metrics needed to explain user latency and pipeline health.

## Primary scope
- `Prometheus metrics/config`
- `Gateway Metrics UI`
- `vLLM metrics`
- `Kafka/Rabbit queue metrics`
- `docs`

## Required behavior
- Define chat availability, TTFT/turn p95, ingestion completion, retrieval success and benchmark-independent quality signals.
- Expose queue lag/backlog and vLLM/GPU pressure where available.
- Keep labels bounded.
- Separate live vs eval traffic.
- Build panels around SLO questions.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorb old FRONT-03 Metrics UI cleanup while touching panels/config.

## Non-goals
- No high-cardinality identifiers.

## Validation
- Metrics tests
- Prometheus config validation
- Frontend Metrics tests

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
