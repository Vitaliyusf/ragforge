# BMARK-13C — Persistent Benchmark Center restore + live progress UI

**Branch:** `feat/benchmark-persistent-ui`

## Goal
Restore benchmark state from the backend after navigation, refresh or browser reopen, and show truthful live item progress.

## Dependencies
- BMARK-13A
- BMARK-13B

## Scope
- BenchmarkCenter components
- `useBenchmarkRuns`
- benchmark frontend service calls
- focused Vitest
- frontend production build

## Required restoration
Backend/Mongo is authoritative.

On mount/dataset selection:

```text
list benchmark runs for dataset
        ↓
active run exists?
  yes -> restore + poll
  no  -> show latest terminal run
```

Required:

```text
navigate away -> return -> same run
refresh -> same run
close/reopen browser -> run/result restored
clear localStorage -> still works
```

localStorage may remember a selected run id only as convenience, never as source of truth.

## UI progress
Show two independent concepts.

### Overall
```text
1 / 3 executable phases complete
```

Do not invent a weighted global percentage.

### Current phase
```text
End-to-end
18 / 30   60%

Processed            18
Successful            15
Guardrail blocked      2
Failed                 1
In flight              3

Elapsed             06:21
Last progress       11 sec ago
```

Use existing design-system components.

## Stall visibility
When `last_progress_at` is conservatively old relative to real timeout behavior, show a non-fatal warning such as:

```text
Possible stall
No benchmark item has completed for 2m 14s.
```

Do not automatically cancel a run from this warning.

## UX
While active show:

```text
Safe to leave this page.
The benchmark runs on the server and progress is saved automatically.
```

Polling failure must preserve last-known state and show a connection/update warning; it must not mark the server job failed.

Keep current/next/unsupported phases visible and exclude unsupported phases from executable denominator.

Clearly distinguish:
```text
Golden Set / Dataset
Benchmark Run
Diagnostic ZIP
```

## Non-goals
- no full history browser
- no immutable export work
- no process/container recovery
- no backend scoring changes

## Required tests
1. Active benchmark restored on mount.
2. Polling resumes after remount.
3. Latest terminal run shown when no active run.
4. Progress bar uses completed/total.
5. Overall count excludes unsupported phases.
6. Guardrail blocked distinct from failed.
7. Missing legacy progress renders safely.
8. Polling failure preserves state.
9. Visibility-aware polling remains correct.
10. Cleanup aborts requests.
11. Safe-to-leave message shown.
12. Dataset/export naming not conflated.

## Validation
Focused Vitest, then:

```powershell
cd frontend
npm run build
```

## Manual gate
During Smoke30:
1. observe progress;
2. navigate away and return;
3. refresh;
4. close/reopen browser;
5. verify same benchmark restored and no duplicate run.

## Final report
Return restoration design, polling/progress UI behavior, changed files, Vitest counts, build result, and manual checks remaining. Do not commit or push.
