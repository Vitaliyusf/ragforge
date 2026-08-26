# BMARK-13E — Benchmark history + historical ZIP download UI

**Branch:** `feat/benchmark-history-ui`

## Goal
Let an admin return hours or days later, find prior benchmark runs, inspect them, and download their diagnostic ZIPs again.

## Dependencies
- BMARK-13C
- BMARK-13D

## Scope
- recent benchmark history UI
- existing list/get APIs
- historical-run selection
- historical download action
- focused frontend tests

## Required UI
Show a bounded newest-first history, for example:

```text
Benchmark history

Aug 26 20:14   Smoke30   completed   [View] [Download ZIP]
Aug 26 18:42   Smoke30   partial     [View] [Download ZIP]
Aug 25 22:11   Smoke30   failed      [View] [Download ZIP]
```

Useful fields:
- dataset name/version
- status
- created/started/finished time
- benchmark id
- current phase for active jobs
- compact headline metrics already available

Do not render all per-item data in the list.

Selecting a historical run shows its persisted phase state, progress/final counters, summary and timestamps. It must not start a new benchmark.

Terminal states supported by backend export should expose Download ZIP (completed/partial/failed/interrupted as applicable).

Download must request the historical export again by `benchmark_id`; do not depend on a browser-local ZIP.

History is reconstructed from backend APIs after browser reopen. No localStorage dependency.

Keep the first implementation bounded (for example recent 20). Do not build a large pagination subsystem solely for this task.

## Non-goals
- no execution changes
- no progress persistence changes
- no snapshot semantics changes
- no crash recovery
- no BMARK-14 comparison UI

## Required tests
1. History loads newest-first.
2. Multiple statuses render correctly.
3. Running row remains active.
4. Historical terminal run can be selected.
5. Selecting history does not start a run.
6. Download availability follows backend terminal-state contract.
7. Download uses benchmark id.
8. Remount reconstructs history from server.
9. Empty state is clear.
10. API failure preserves current view.
11. Long ids/names do not break layout.

## Validation
Focused Vitest +:

```powershell
cd frontend
npm run build
```

## Manual gate
1. finish Smoke30;
2. leave page;
3. close browser;
4. reopen later;
5. find run in history;
6. open it;
7. download ZIP;
8. verify correct benchmark/version.

## Final report
Return history UX, list/get/download behavior, terminal rules, changed files, Vitest counts and build result. Do not commit or push.
