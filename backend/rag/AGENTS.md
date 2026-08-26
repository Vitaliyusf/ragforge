# RAG Service Instructions

Applies to `backend/rag/**`.

Follow root and backend instructions.

## RAG invariants
- Preserve Regular/Extended semantics unless the task explicitly changes them.
- Reuse existing eval/tracing/metrics/conversation infrastructure.
- Golden ground truth belongs only to eval overlays, never live retrieval.
- Keep production context K distinct from eval candidate depth.
- Do not call dedupe/sort a learned reranker.
- `null` means unmeasured.
- Bounded concurrency must preserve tenant/trace context.

## Navigation
For eval/benchmark tasks:
1. task spec first;
2. current eval store/runner/parser/tests;
3. expand to Files/Gateway/Vector/Frontend only when a direct contract/call path requires it.

Do not pre-scan the entire backend/frontend.

## Validation
During implementation:
- focused eval tests;
- changed-file Ruff.

Run the whole RAG service suite once only if the change materially affects:
- eval runner lifecycle;
- RPC behavior;
- persistence;
- concurrency;
- security/tenant behavior;
- broad retrieval behavior.

For a NO-OP task, run only acceptance-named eval tests.

Do not disable pytest plugin autoload or skip async tests to claim the RAG suite passed.
