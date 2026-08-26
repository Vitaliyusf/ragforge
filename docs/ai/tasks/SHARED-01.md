# SHARED-01 — Consolidate shared service contracts

**Branch:** `refactor/shared-service-contracts`

## Goal
Reduce duplicated CORS/logging/errors/messaging/envelope scaffolding across services.

## Problem
Copied infrastructure drifts and forces compatibility wrappers/sys.path hacks.

## Primary scope
- `backend/shared`
- `service-specific wrappers/interfaces/envelopes`
- `tests`

## Required behavior
- Only move contracts truly shared by multiple services.
- Remove internal-service CORS where browser access is unnecessary rather than centralizing unnecessary middleware.
- Eliminate sys.path/importlib shared-module workarounds where packaging allows.

## Acceptance
- No behavior/security regression and duplicates are actually removed, not wrapped in another layer.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
