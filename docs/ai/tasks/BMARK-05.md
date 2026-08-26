# BMARK-05 — Benchmark dataset reproducibility

**Branch:** `feat/eval-dataset-reproducibility`

## Goal
Add canonical version/hash and stale-label gating to prepared benchmark datasets.

## Problem
Run comparisons are meaningless if labels mutate or point to old index chunks.

## Primary scope
- `eval store/runner`
- `validation/UI/tests`

## Required behavior
- Deterministic scoring-content hash/version.
- Run snapshots ID/version/hash.
- Stale labels reported and not counted as misses.
- Backward compatibility.

## Acceptance
- Hash/version/stale/historical-run tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
