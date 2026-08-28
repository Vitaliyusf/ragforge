---
paths:
  - "backend/**/*.py"
---
# Backend rules

- Preserve auth/tenant boundaries and existing RPC/event contracts.
- Reuse service/repository abstractions before adding new cross-service coupling.
- Avoid blocking I/O in async request paths.
- During implementation run changed-file Ruff plus focused tests; use the matching lane from `scripts/ai/check.py` when broader domain coverage is justified.
- Environment/plugin failure is `BLOCKED`, not permission to silently skip tests.
