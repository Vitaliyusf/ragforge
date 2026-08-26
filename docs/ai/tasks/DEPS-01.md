# DEPS-01 — Staged dependency modernization

**Branch:** `chore/upgrade-python-web-stack`

## Goal
Upgrade selected Python web/runtime dependencies with isolated compatibility validation.

## Problem
Several pinned packages lag current maintained versions; mass upgrade would obscure breakage.

## Primary scope
- `FastAPI/Uvicorn/Pydantic-settings/PyMongo as selected by current audit`
- `lock/requirements/tests`

## Required behavior
- Upgrade a coherent small set only.
- Read release/migration notes for breaking changes.
- Do not combine LangGraph/sentence-transformers/Kafka major upgrades here.

## Acceptance
- Affected backend suites pass; startup/config behavior preserved.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
