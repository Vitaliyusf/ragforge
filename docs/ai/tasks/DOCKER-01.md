# DOCKER-01 — Container image and dependency cleanup

**Branch:** `chore/container-image-cleanup`

## Goal
Reduce duplicated Dockerfiles/runtime dependencies and image attack surface without behavior changes.

## Problem
Python service images duplicate setup, include some test/optional heavyweight dependencies, and frontend runtime may copy more than needed.

## Primary scope
- `Dockerfiles`
- `requirements split`
- `Next standalone output`
- `build cache/test validation`

## Required behavior
- Move test-only deps out of production where safe.
- Split optional heavyweight LLM backends if unused by default runtime.
- Consider shared base pattern without hiding service-specific needs.
- Use Next standalone runtime if compatible.

## Acceptance
- Images build and affected tests run; runtime functionality preserved.

## Measurement
Image size/build time/startup/RSS and vulnerability scan before/after where available.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
