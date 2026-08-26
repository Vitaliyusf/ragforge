# EVAL-06 — Pipeline-mode evaluation

**Branch:** `feat/eval-pipeline-modes`

## Goal
Evaluate base retriever, Regular and Extended behavior truthfully.

## Problem
Evaluation mode (retrieval/end-to-end) and RAG pipeline mode are separate axes and must not be conflated.

## Primary scope
- `eval_runner/store`
- `RAG request mode`
- `Gateway eval DTO/API`
- `Eval UI/tests`

## Required behavior
- Separate `evaluation_mode` from `pipeline_mode`.
- End-to-end Extended invokes the real Extended graph.
- Base retrieval is labelled base retriever, not Extended retrieval.

## Acceptance
- Run metadata distinguishes both axes and tests prove Regular/Extended use different graph mode values.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
