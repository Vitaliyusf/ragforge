# EVAL-01 — Eval candidate depth correctness

**Branch:** `fix/eval-candidate-depth`

## Goal
Ensure retrieval eval requests enough candidates for every Recall@K it reports.

## Problem
Recall@10/20 is invalid if retrieval only returns production context depth. Keep production context K separate from eval candidate depth.

## Primary scope
- `backend/rag/app/services/eval_runner.py`
- `backend/rag/app/services/conversation_backend_client.py`
- `backend/rag/app/core/config.py`
- `RAG eval tests`

## Required behavior
- Eval candidate depth is at least max reported K.
- Production `top_k_documents` behavior is unchanged.
- Run snapshot records actual candidate depth.

## Current-state note
Known as merged in the repository snapshot observed on 2026-08-26; verify current main and make no changes if already satisfied.

## Acceptance
- A relevant result below production K but within rank 20 is observable by Recall@20.
- RAG tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
