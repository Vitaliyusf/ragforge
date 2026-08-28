---
paths:
  - "frontend/**/*.{js,jsx,ts,tsx}"
---
# Frontend rules

- Preserve existing API contracts, cancellation behavior, routing, and shared state semantics.
- Run only relevant Vitest files during implementation.
- Run a production build only for routing, shared shell/state, build configuration, or production-impacting integration changes.
- Do not rerun the full frontend suite locally after unrelated backend or memory-only edits; CI owns broad coverage.
