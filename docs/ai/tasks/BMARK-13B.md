# BMARK-13B — Persisted item-level benchmark progress

**Branch:** `feat/benchmark-item-progress`

## Goal
Persist truthful per-item progress for the currently running phase so the UI can distinguish active work from a stalled run.

## Problem
During long E2E phases the benchmark can remain `running` for minutes while current progress only advances meaningfully at phase boundaries.

## Scope
- benchmark/eval progress persistence
- item counters
- progress timestamps
- bounded timeout integration only if a real gap exists
- benchmark GET/list response shape if needed
- focused backend tests

## Required persisted progress
Expose/persist the project-consistent equivalent of:

```text
current_phase
items_total
items_completed
items_in_flight
items_succeeded
items_guardrail_blocked
items_failed
items_timed_out
phase_started_at
last_progress_at
elapsed_ms or timestamps sufficient to derive it
```

`items_completed` means items that reached terminal outcomes. Reconcile counters without double counting.

With concurrency > 1, do not invent one sequential `current item`.

Example:

```text
total       30
completed   17
in_flight    3
succeeded   14
blocked      2
failed       1
```

Reuse the natural persisted per-item completion point in EvalRunner/EvalStore. Do not write on every generated token and do not mutate progress just because the browser polls.

Update `last_progress_at` whenever meaningful persisted progress advances.

## Timeout rule
Inspect existing graph/RPC/LLM timeouts first. If they already bound item execution, reuse them. Only add a new timeout where a real indefinite-wait gap exists.

A true timed-out item must become terminal and must not leave the phase running forever when continuation is safe.

## Non-goals
- no progress UI
- no browser history/restore
- no guardrail policy changes
- no Celery/Temporal/Redis queue
- no process-restart recovery
- no retrieval algorithm changes

## Required tests
1. Benchmark starts at 0/N.
2. Terminal item increments persisted progress.
3. Concurrent completions cannot double-count.
4. Success/block/failure/timeout counters reconcile.
5. `last_progress_at` advances.
6. Poll/read APIs do not mutate progress.
7. Unsupported retrieval phase does not inflate executable denominator.
8. Phase transition preserves final counters.
9. Timeout becomes terminal if handled here.
10. Legacy benchmark documents normalize safely.

## Validation
Run doctor once, focused tests, Ruff changed files. Because persistence + async/concurrency behavior changes, run RAG affected-service suite once near completion.

## Manual gate
Run Smoke30 and observe API state during E2E:

```text
0/30 -> ... -> 30/30
last_progress_at moves
counters reconcile
no duplicate accounting
```

## Final report
Return persisted schema, update points, concurrency strategy, timeout decision, tests, and manual checks remaining. Do not commit or push.
