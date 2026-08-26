# FRONT-01 — Batch chat streaming renders

**Branch:** `perf/chat-stream-rendering`

## Goal
Reduce React work from token-by-token reducer/context updates.

## Problem
Every streamed token currently causes large immutable state/context/message reconstruction.

## Primary scope
- `ChatContext/reducer/stream handlers`
- `focused chat tests`

## Required behavior
- Buffer tokens in ref/store and flush at requestAnimationFrame or bounded 25–50ms cadence.
- One live source of streaming text; finalize message on done.
- Preserve cancel/error/citation behavior.

## Acceptance
- Tests prove token order/final answer; render/update count is materially lower under a synthetic token burst.

## Measurement
Compare state updates/renders and main-thread time for a fixed token stream.

## Task rules
- Follow root and scoped AGENTS.md/CLAUDE.md.
- Inspect current code before editing; current implementation wins over stale assumptions.
- Keep this branch limited to this task.
- Run focused tests, then broader affected checks.
- Do not commit or push; return a recommended Conventional Commit message.
