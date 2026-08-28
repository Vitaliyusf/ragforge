# BMARK-15 — Benchmark Center hardening

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Branch:** `chore/benchmark-center-hardening`

## Goal
Security/storage/performance/integration hardening after the complete benchmark workflow exists.

## Problem
The feature should not leave unbounded artifacts, N+1 lookups, unsafe export, or weak tenant boundaries.

## Primary scope
- `benchmark/eval backend+frontend touched by BMARK-01..14`
- `integration/security tests`

## Required behavior
- Admin/tenant enforcement, input/item/export limits, retention/TTL, explicit truncation, temp cleanup, index/N+1 review.
- Full prepare→run→export integration test.

## Acceptance
- Relevant backend suites, Ruff/mypy, Vitest and production build pass; remaining risks documented.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
