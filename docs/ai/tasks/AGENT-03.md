# AGENT-03 — Memory agent evaluation harness

**Branch:** `feat/memory-agent-evals`

## Goal
Measure real tool-agent correctness, safety and efficiency reproducibly.

## Problem
Unit tests alone do not quantify agent behavior across realistic/adversarial conversations.

## Primary scope
- `benchmarks/agent`
- `machine-readable dataset/results`
- `memory test helpers`

## Required behavior
- Cases for add/noop/update/delete/dedupe/conflict/privacy/injection/budgets.
- Metrics for success/tool selection/invalid calls/unnecessary mutations/injection/tool count/latency.
- Store model/config/git metadata.

## Acceptance
- Harness supports deterministic fake mode and clearly separate real-model mode; no fabricated results.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
