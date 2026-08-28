---
paths:
  - "backend/rag/**/*.py"
---
# RAG service rules

- Preserve Regular/Extended semantics unless the active task changes them.
- Golden ground truth belongs only to eval overlays, never live retrieval.
- Keep production context K separate from eval candidate depth.
- `null` means unmeasured; do not fabricate metrics.
- Bounded concurrency must preserve tenant and trace context.
- Start from current RAG implementation/tests; expand to Files/Gateway/Vector/Frontend only through a proven contract/call path.
