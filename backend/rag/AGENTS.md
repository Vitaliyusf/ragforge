# RAG Service Instructions

Applies to `backend/rag/**`.

- Preserve Regular/Extended semantics unless the task explicitly changes them.
- Reuse existing eval, tracing, metrics-facts and conversation graph infrastructure; do not create parallel systems.
- Golden ground truth belongs to eval overlays, never live production retrieval.
- Production instrumentation may record candidate IDs/ranks/scores/provenance; keep text bounded/admin-only.
- Keep production context K distinct from eval candidate depth.
- Do not call dedupe/sort a learned reranker.
- `null` means unmeasured; preserve denominators for rates.
- Concurrency must be bounded and preserve tenant/trace context.
- Behavior-neutral graph refactors and retrieval algorithm changes should be separate tasks.

## Validation
Follow root progressive validation. Prefer `python scripts/ai/check.py fast ...` while iterating and `python scripts/ai/check.py service ...` once near task completion. Avoid repeated isolated `uv` environments.
