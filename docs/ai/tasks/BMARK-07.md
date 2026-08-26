# BMARK-07 — Automatic benchmark manifest

**Branch:** `feat/benchmark-run-manifest`

## Goal
Capture safe build/dataset/runtime/model configuration automatically.

## Problem
A benchmark is not reproducible if Git/config/model details must be remembered manually.

## Primary scope
- `new benchmark_manifest module`
- `safe build-info/config plumbing`
- `tests`

## Required behavior
- Explicit allowlist of Git/build/dataset/RAG/embedding/chunk/vector/LLM/software metadata.
- Support injected RAGFORGE_GIT_SHA/BRANCH/BUILD_TIMESTAMP.
- Unknown=null; never dump env/secrets.

## Acceptance
- Manifest serializes with missing values and secret-leak regression tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
