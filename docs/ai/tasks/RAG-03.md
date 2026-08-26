# RAG-03 — Token-aware diverse context assembler

**Branch:** `feat/rag-context-assembler`

## Goal
Select evidence by budget and diversity instead of blindly taking first K.

## Problem
First-K selection can waste context on redundant neighboring chunks and ignore prompt token budget.

## Primary scope
- `new context_assembler.py`
- `conversation_graph.py`
- `RAG config/tests`

## Required behavior
- Explicit evidence token budget.
- Deterministic selection.
- Score + redundancy/source diversity consideration.
- Preserve citation numbering and diagnostics.

## Acceptance
- Tests cover token budget, redundancy, multi-document diversity, oversized chunk and empty context.

## Measurement
Compare answer quality/claim coverage, evidence tokens and E2E latency.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
