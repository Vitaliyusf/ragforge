# RAGForge CI / Test Environment Task Pack

Recommended order:

1. `CLEAN-02` — restore repo-wide Ruff green.
2. `CI-02` — harden/split GitHub Actions and add the Python 3.11 source of truth.
3. `DEPS-06` — centralize Python test dependencies and remove conflicting runtime pytest pins.
4. `DEV-01` — make the agent doctor detect local Python/test-tool drift immediately.

These are intentionally separate tasks:
- CLEAN-02 changes application source only to restore lint.
- CI-02 changes workflow/version alignment.
- DEPS-06 changes dependency ownership/install semantics.
- DEV-01 changes agent-local environment diagnostics.

Do not combine all four into one PR unless explicitly requested.
