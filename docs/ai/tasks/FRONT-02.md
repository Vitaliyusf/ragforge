# FRONT-02 — Files UI/data-flow scalability

**Branch:** `perf/files-data-flow`

## Goal
Reduce unnecessary file polling/render passes and sequential upload latency.

## Problem
Full list polling every 5s, repeated status computation and sequential multi-file uploads do not scale.

## Primary scope
- `useFiles.js`
- `FilesTab.jsx`
- `file API pagination/filter only if required`
- `tests`

## Required behavior
- Adaptive/visibility-aware polling.
- Bounded parallel uploads.
- Normalize status once per list pass.
- Split cohesive FilesTab sections when useful.
- Plan/implement server pagination when dataset size justifies it.

## Acceptance
- No unbounded Promise.all; hidden/idle polling reduced; upload/file behavior tests pass.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
