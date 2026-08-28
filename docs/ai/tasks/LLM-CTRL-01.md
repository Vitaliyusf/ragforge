# LLM-CTRL-01 — Unify LLM control plane and simplify execution/provider ownership

**Order:** 16  
**Phase:** 2 Simplification  
**Priority:** P1  
**Branch:** `refactor/llm-control-plane`  
**Depends on:** `CONFIG-01`, `VALIDATE-01`

## Goal
Make llm_agent the canonical typed LLM execution boundary and fold LLMService/provider/control-plane cleanup into that ownership change.

## Primary scope
- `backend/llm_agent/app/services/llm_service.py`
- `provider adapters`
- `prompt registry/config`
- `Memory LLM callers`
- `requirements/Dockerfile`
- `tests`

## Required behavior
- Route Memory title/summary/curation model calls through typed llm_agent requests unless a measured exception is documented.
- Split execution into cohesive plan/render/invoke/decode/validate/telemetry responsibilities with one façade.
- Decide supported providers; remove unused provider code/deps or isolate optional builds.
- Remove prompt-registry compatibility re-export after migration.
- Use one structured-output and error/finish-reason evidence policy.
- Keep accepted vLLM runtime unchanged.

## Local refactor budget
This task may perform behavior-neutral cleanup only in code it already needs to touch.

- If a touched production file is already a hotspot (>500 lines or clearly multi-responsibility), evaluate extracting the concern changed by this task.
- Prefer deleting/moving an obsolete path over adding a wrapper around it.
- At most 2 cohesive new production modules unless this task explicitly requires more.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, `v2`, or parallel compatibility layers without a concrete domain owner.
- Do not split code merely to satisfy a line-count target.
- Remove stale narrative comments in touched code; keep comments for invariants, security, recovery, protocol semantics, or non-obvious trade-offs.
- Final report: production files added/deleted, hotspot before/after line counts where relevant, obsolete paths removed, and new dependencies.


**Task-specific refactor target:** Absorbs old LLMService refactor; llm_service.py should materially shrink without dozens of tiny files.

## Non-goals
- No model/vLLM retuning.

## Validation
- Focused LLM request-type tests
- Full LLM suite
- Affected Memory tests
- Ruff
- mypy on changed contracts
- Image build

## Execution rules
- Current source wins over stale assumptions.
- Preserve unrelated dirty files; never reset/stash/revert/clean.
- Do not commit or push.
- Do not run `doctor` as a generic prerequisite.
- Do not repair `.venv` as part of normal task work.
- If the local Python environment is unsuitable, use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Iterate with focused tests; run the affected service suite once near completion.
- Do not run expensive benchmarks unless the task explicitly requires them.
