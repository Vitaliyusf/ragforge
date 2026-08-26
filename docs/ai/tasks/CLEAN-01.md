# CLEAN-01 — Remove confirmed dead compatibility code

**Branch:** `chore/remove-dead-compat-code`

## Goal
Delete duplicate/legacy modules only after proving they have no live callers.

## Problem
Compatibility paths retained after refactors increase maintenance and confuse source-of-truth ownership.

## Primary scope
- `known embedding legacy duplicate handler module`
- `Gateway messaging compatibility stubs`
- `other items found by reference search`

## Required behavior
- Repo-wide reference verification before deletion.
- Do not delete feature-flagged/optional code without proving it is intentionally obsolete.
- Update imports/tests/docs only as needed.

## Acceptance
- All affected service tests pass; no remaining import/reference to removed symbols.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
