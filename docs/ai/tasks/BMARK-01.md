# BMARK-01 — Benchmark dataset parser

**Branch:** `feat/benchmark-dataset-parser`

## Goal
Import JSON/JSONL golden sets into one canonical schema.

## Problem
Users should not manually reshape benchmark datasets before every run.

## Primary scope
- `RAG eval schemas/store/parser`
- `focused tests`

## Required behavior
- Support authoring format (`expected_file_names`, `expected_facts`) and current eval IDs format.
- Bound input/items, item-level errors, duplicate IDs.
- No file resolution yet.

## Acceptance
- Equivalent JSON/JSONL normalize identically; malformed row errors identify item/field.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
