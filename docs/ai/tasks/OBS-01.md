# OBS-01 — Separate eval and live operational metrics

**Branch:** `feat/metrics-traffic-class`

## Goal
Prevent synthetic benchmark traffic from polluting live traffic metrics.

## Problem
Eval requests use real embedding/vector/LLM paths and can distort Prometheus request/latency series.

## Primary scope
- `backend/shared/metrics.py`
- `eval request context`
- `embedding/vector/LLM instrumentation`
- `Gateway PromQL/tests`

## Required behavior
- Bounded `traffic_class` label with live/eval only where needed.
- Existing traffic defaults live.
- Operational UI defaults to live.

## Acceptance
- Eval run changes eval series but not live request-rate/latency series.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
