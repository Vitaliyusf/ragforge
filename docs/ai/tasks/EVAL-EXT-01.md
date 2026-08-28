# EVAL-EXT-01 — External eval calibration and Eval subsystem decomposition

**Order:** 45  
**Phase:** 6 Quality & Observability  
**Priority:** P2  
**Branch:** `feat/eval-calibration`  
**Depends on:** `QUAL-01`, `OBS-TRACE-01`

## Goal
Use Ragas/external metrics to calibrate the internal harness while locally decomposing oversized eval runner/store modules.

## Primary scope
- `eval_runner.py`
- `eval_store.py`
- `benchmark/eval adapters`
- `optional Ragas adapter`
- `tests`

## Required behavior
- Keep internal release harness authoritative.
- Run external metrics on fixed selected datasets.
- Record disagreements instead of replacing definitions.
- Extract dataset/run/benchmark repository and scoring/execution concerns into a small number of cohesive modules.
- No second persistence model.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorbs old Eval refactor task.

## Non-goals
- No wholesale eval framework replacement.

## Validation
- Eval/benchmark suites
- Selected calibration run

## Measurement
- Metric agreement/disagreement, runtime/cost.

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
