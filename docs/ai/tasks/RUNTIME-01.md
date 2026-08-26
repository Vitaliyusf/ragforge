# RUNTIME-01 — Runtime and container hardening

**Branch:** `chore/production-runtime-hardening`

## Goal
Upgrade unsupported frontend runtime and reduce container privilege/attack surface.

## Problem
Production hygiene requires supported Next.js plus non-root/readiness/container restrictions.

## Primary scope
- `frontend package/lock/config`
- `application Dockerfiles`
- `compose health/security settings`
- `tests/docs`

## Required behavior
- Supported Next migration with tests/build.
- Non-root services where feasible.
- Live vs ready health semantics.
- Read-only/cap-drop/no-new-privileges only where compatible.

## Acceptance
- Frontend build/tests pass; compose validates; services run with intended writable paths/dependencies.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
