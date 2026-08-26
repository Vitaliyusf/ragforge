# FRONT-03 — Metrics frontend component consolidation

**Branch:** `refactor/metrics-components`

## Goal
Split oversized Eval/Pipeline panels and remove duplicated metric display helpers.

## Problem
Metrics panels repeat Stat/PromWidget/row/bucket rendering and large page components own too many concerns.

## Primary scope
- `frontend/src/features/metrics/components`
- `hooks/services/tests`

## Required behavior
- Extract focused shared primitives only where semantics truly match.
- Split Eval/Pipeline into cohesive cards/sections.
- No generic schema-driven mega-renderer.

## Acceptance
- Existing UI behavior/tests preserved and component responsibilities become smaller/clearer.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
