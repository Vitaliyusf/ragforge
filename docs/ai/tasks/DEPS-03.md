# DEPS-03 — Kafka client upgrade

**Branch:** `chore/upgrade-kafka-client`

## Goal
Modernize kafka-python independently from delivery-semantics changes.

## Problem
A major client upgrade and a delivery-semantics refactor together make failures hard to attribute.

## Primary scope
- `Kafka dependency/shared base/affected service tests`

## Required behavior
- Keep behavior equivalent on this branch.
- Address API/config deprecations.
- Do not change auto/manual commit strategy here unless required for compatibility.

## Acceptance
- Affected producer/consumer unit/integration tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
