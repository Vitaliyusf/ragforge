# CONC-11 — Bound frontend polling, stale requests and client-side fan-out

**Phase:** Frontend performance  
**Priority:** P2  
**Branch:** `perf/frontend-network-control`  
**Depends on:** backend concurrency contracts stable

## Goal

Reduce avoidable browser/network work and prevent stale/out-of-order responses without changing product behavior.

## Preserve what is already good

`FilesTab` already uses bounded bulk concurrency (`BULK_CONCURRENCY=4`). Keep the bound unless measurement supports another value.

## Audit targets

- repeated health/metrics polling;
- model-download `setInterval` polling;
- ChatContext retry timers and concurrent resource loads;
- request cancellation on navigation/unmount;
- duplicate identical GETs;
- stale response overwriting newer state;
- hidden-tab/background polling;
- multiple dashboard panels requesting the same source separately.

## Required behavior

Where applicable:

- use `AbortController` for superseded HTTP requests;
- coalesce identical in-flight GETs at an appropriate data-service boundary;
- pause/decrease noncritical polling when page is hidden;
- add jitter/backoff to repeated failure polling;
- prevent overlapping `setInterval` async calls;
- stop polling on terminal state/unmount;
- ensure response generation/version prevents stale overwrite;
- use `Promise.all` only for truly independent bounded calls.

Do not introduce a frontend data library unless it clearly removes more custom code than it adds.

## Measurement

Capture:
- requests/min on idle Metrics/Health/Models pages;
- duplicate request count;
- bytes transferred;
- long-task/main-thread evidence if relevant;
- user-visible refresh latency.
## Validation — MINIMAL

Follow `CONC-VALIDATION-POLICY.md`.

For this task run only:

- the smallest focused regression test(s) that prove the changed behavior;
- Ruff on changed Python files;
- `git diff --check`.

Do **not** run a full service suite, repository suite, broad mypy, Docker rebuild, or load benchmark unless this task explicitly owns that measurement.

If the task includes a benchmark section, run only the smallest benchmark needed to prove this task's own performance claim. The full load campaign belongs to `CONC-99`.

## Execution rules

- Current source wins.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not repair `.venv`.
- Use isolated Python 3.12 fallback only if needed.
- Once the focused regression is green, STOP.
