# TYPES-01 — Strengthen critical contracts and type checking

**Branch:** `refactor/typed-contracts`

## Goal
Improve type safety at high-risk backend/frontend boundaries incrementally.

## Problem
Strict typing is uneven and dynamic payload normalization can hide contract drift.

## Primary scope
- `RAG/eval/memory/vector/files critical schemas`
- `mypy config for cleaned modules`
- `frontend socket/eval/metrics contract layer`

## Required behavior
- Tighten selected modules only, not repo-wide strict switch.
- Centralize critical frontend payload shapes via JSDoc/TS islands as appropriate.
- No full frontend rewrite.

## Acceptance
- Newly strict modules pass; runtime API remains compatible; tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
