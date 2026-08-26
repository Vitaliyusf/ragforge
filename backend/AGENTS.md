# Backend Instructions

Applies to `backend/**`.

Follow the root `AGENTS.md`.

## Validation
- During implementation: changed-file Ruff + focused tests only.
- Do not run every backend service locally.
- Run an affected service suite once only for a cross-cutting/high-risk change in that service.
- Shared/backend-wide validation belongs to CI unless the task explicitly changes shared infrastructure/contracts.
- Do not run mypy outside a justified typed-contract/CI scope merely because Python changed.
- Environment collection/plugin failure is `BLOCKED`, not permission to skip tests.

## Architecture
- Preserve tenant/auth boundaries.
- Prefer existing repositories/services/RPC contracts.
- Avoid new cross-service coupling unless required by the task.
