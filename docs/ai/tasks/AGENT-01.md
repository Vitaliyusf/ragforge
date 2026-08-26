# AGENT-01 — Memory agent server-side mutation policy

**Branch:** `feat/memory-agent-policy`

## Goal
Enforce deterministic authorization/budgets around memory tool calls.

## Problem
Prompt instructions are not a security boundary for destructive add/update/delete tools.

## Primary scope
- `memory_agent.py`
- `new policy/tool executor`
- `memory tests`

## Required behavior
- Scope from server identity only.
- Update/delete only IDs listed/authorized in current run.
- Budgets for adds/updates/deletes/tool calls/steps/runtime/content.
- Auditable denials.

## Acceptance
- Injection, unknown ID, cross-user ID and budget-abuse tests leave data unchanged.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
