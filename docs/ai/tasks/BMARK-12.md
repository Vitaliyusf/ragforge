# BMARK-12 — Diagnostic ZIP export

**Branch:** `feat/benchmark-diagnostic-export`

## Goal
Download one safe admin/tenant-scoped ZIP containing all benchmark evidence.

## Problem
External analysis should require one file, not manual logs/config/screenshots.

## Primary scope
- `admin export API`
- `server-side ZIP generation`
- `tests`

## Required behavior
- README, manifest, canonical dataset/validation, summary/per-item, traces, metrics, runtime info, errors.
- Valid JSON/null semantics, bounded size, safe filename/temp cleanup, no secrets/cross-tenant data.

## Acceptance
- ZIP structure/JSON/auth/cross-tenant/secret/path-traversal/partial-run tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
