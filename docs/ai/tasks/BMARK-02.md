# BMARK-02 — Golden set import UI

**Branch:** `feat/benchmark-dataset-import-ui`

## Goal
Upload or paste JSON/JSONL from Metrics/Eval.

## Problem
Benchmark setup should not require CLI/manual file manipulation.

## Primary scope
- `metrics benchmark components`
- `metrics/eval service/hook`
- `frontend tests`

## Required behavior
- File upload + textarea paste + validate/reset.
- Render precise backend validation.
- Do not enlarge EvalPanel unnecessarily.

## Acceptance
- JSON, JSONL, malformed and server-error UI tests plus production build.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
