# DEPS-05 — LangGraph major-version migration

**Branch:** `chore/upgrade-langgraph`

## Goal
Upgrade LangGraph only after graph behavior is well isolated and regression-tested.

## Problem
A 0.x→1.x migration is architectural, not routine dependency housekeeping.

## Primary scope
- `RAG graph/checkpoint integration`
- `Files only if it still truly uses LangGraph`
- `requirements/tests`

## Required behavior
- Read official migration notes.
- Preserve graph nodes/edges/checkpoints/stream semantics.
- No unrelated RAG algorithm changes.

## Acceptance
- Full RAG graph tests and recovery/checkpoint tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
