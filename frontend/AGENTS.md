# RAGForge Frontend Instructions

Applies to `frontend/**`.

- The current `package.json` versions are authoritative until an explicit upgrade task.
- Avoid making large Chat/Eval/Files containers larger when cohesive extraction is possible.
- Keep server state, local UI state and high-frequency streaming buffers distinct.
- Avoid React state/context updates per token; batch high-frequency updates.
- Polling should be visibility-aware, stop on terminal states and propagate a real AbortSignal to `fetch`.
- Reuse `src/lib/http` instead of duplicating HTTP/retry/error logic.
- Preserve accessibility and stable domain IDs as React keys.
- Do not add dependencies for behavior existing primitives/CSS can provide.
- Run focused Vitest; production-impacting frontend changes also run `npm run build`.
