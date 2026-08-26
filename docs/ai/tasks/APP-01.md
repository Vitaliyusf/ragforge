# APP-01 — ApplicationRuntime and FastAPI dependency ownership

**Branch:** `refactor/service-runtime-containers`

## Goal
Replace fragile module-global service singletons/deferred imports with lifespan-owned runtime containers.

## Problem
Gateway/RAG and other services build many runtime objects as globals/import-time state, complicating tests/lifecycle/DI.

## Primary scope
- `start with Gateway runtime/deps; extend only as task explicitly allows`
- `FastAPI lifespan/tests`

## Required behavior
- Runtime object on app.state or equivalent explicit DI.
- No import-time network/database connection.
- Clean shutdown ownership.

## Acceptance
- Gateway tests pass and deps no longer import mutable singletons from `app.main`.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
