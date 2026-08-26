# CHAOS-01 — Controlled chaos and recovery suite

**Branch:** `feat/chaos-recovery-tests`

## Goal
Validate data-loss/duplication/recovery semantics under service failures.

## Problem
Retry/recovery claims require kill/replay evidence, not happy-path tests.

## Primary scope
- `tests/chaos or benchmarks/chaos`
- `opt-in runner/docs`

## Required behavior
- Scenarios for embedding/vector/RAG/eval/RabbitMQ/Kafka/vLLM/Mongo/browser disconnect.
- Expected loss/duplicate/recovery semantics per scenario.
- Machine-readable PASS/FAIL + evidence.

## Acceptance
- Chaos suite cannot target production by default and does not hide failures behind its own retry loop.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
