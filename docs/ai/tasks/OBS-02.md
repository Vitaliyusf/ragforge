# OBS-02 — Distributed observability, SLOs and GPU telemetry

**Branch:** `feat/distributed-observability`

## Goal
Correlate service stages end-to-end and define operational objectives.

## Problem
Existing IDs/Prometheus metrics are useful but do not form a full cross-service distributed trace/SLO view.

## Primary scope
- `shared observability bootstrap`
- `service propagation`
- `compose observability profile`
- `docs/tests`

## Required behavior
- OpenTelemetry-style trace context across Gateway/RabbitMQ/RAG/downstream.
- No raw private content in attributes.
- Optional Grafana/collector profile.
- GPU telemetry only via safe supported source.
- Initial SLO definitions as targets, not claims.

## Acceptance
- One chat turn can be followed across touched services with a single trace identity.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
