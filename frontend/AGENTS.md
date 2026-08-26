# Frontend Instructions

Applies to `frontend/**`.

Follow root `AGENTS.md`.

## Validation
During implementation:
- run only the relevant Vitest file(s).

Do not run the entire frontend suite locally by default.
GitHub CI owns the full frontend suite.

Run `npm run build` only when the task changes:
- production-impacting API integration;
- routing/navigation;
- shared application shell/state;
- build configuration;
- a cross-cutting component contract.

Small local rendering/component changes normally require only focused component tests.

Do not rerun already passing frontend checks after backend-only or memory-only edits.
