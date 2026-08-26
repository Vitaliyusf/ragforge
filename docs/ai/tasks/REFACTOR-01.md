# REFACTOR-01 — Decompose oversized orchestration modules

**Branch:** `refactor/graph-modules`

## Goal
Split RAG/files orchestration into cohesive modules without changing behavior.

## Problem
Large graph/workflow files make changes and tests difficult.

## Primary scope
- `conversation_graph.py`
- `file_ingestion_graph.py`
- `new cohesive modules/tests`

## Required behavior
- Behavior-neutral move/extraction only.
- Explicit state/dependency boundaries.
- No circular-import explosion or dozens of trivial files.

## Acceptance
- All existing RAG/Files tests pass unchanged in semantics; main orchestration files materially shrink.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
