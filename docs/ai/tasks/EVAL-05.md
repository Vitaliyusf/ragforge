# EVAL-05 — Eval/benchmark leases and crash recovery

**Branch:** `feat/eval-run-leases`

## Goal
Prevent eval or benchmark jobs from remaining falsely `running` after process/container death, and recover unfinished work exactly once where a safe idempotent boundary exists.

## Problem
Browser persistence is not execution durability. The benchmark currently launches in-process async tasks. If the RAG process/container dies, Mongo may still say a run is `running` after the task itself has disappeared.

## Dependencies
Implement after BMARK-13A..13E so recovery can use the final persisted job/progress/export model.

## Scope
- eval-run lease/heartbeat metadata
- benchmark orchestration lease/reconciliation
- RAG startup recovery
- atomic ownership/idempotency boundaries
- explicit interrupted semantics
- focused tests

## Required lease behavior
Use a small persisted lease/heartbeat contract consistent with current stores, conceptually:

```text
worker/owner id
lease/heartbeat timestamp
lease expiry
recovery metadata if useful
```

Do not introduce Celery, Temporal, Redis queues or a new workflow platform.

### Eval runs
```text
fresh valid lease -> leave running
expired lease -> exactly one recovery owner
terminal run -> untouched
```

If an in-flight eval run cannot safely resume, close it explicitly as interrupted/failed according to truthful current semantics. Do not silently replay uncertain work.

### Benchmark orchestration
At startup/reconciliation:
1. preserve terminal phases;
2. inspect current phase `run_id` + eval-run state;
3. never rerun a completed phase;
4. never create a duplicate eval run for an existing phase;
5. resume from the next safe idempotent boundary when provable;
6. otherwise mark explicit `interrupted` rather than permanent `running`.

Minimum guarantee:

```text
service restart cannot leave a permanent false-running benchmark
```

Desired stronger guarantee:

```text
completed phases preserved
safe unfinished work resumes from a proven idempotent boundary
```

Correctness wins over pretending transparent continuation is always possible.

## Idempotency
Use persisted benchmark phase `run_id`, phase status and eval-run status as the primary boundaries. Do not rely only on timestamps or in-memory task existence.

## Logging
Log structured recovery decisions:
```text
fresh lease kept
stale lease claimed
run interrupted
benchmark resumed
completed phase preserved
duplicate recovery skipped
```

Do not log raw eval content.

## Non-goals
- no distributed workflow platform
- no scorer redesign
- no metric/retrieval changes
- no replay of completed work
- no Kubernetes dependency

## Required tests
1. Fresh lease remains running.
2. Expired lease is recoverable.
3. Two recovery attempts cannot both own the same stale run.
4. Completed/failed terminal eval runs remain untouched.
5. Unresumable stale eval run becomes explicit terminal state.
6. Completed benchmark phase is not rerun.
7. Existing phase `run_id` prevents duplicate phase run.
8. Queued next phase resumes only after safe reconciliation.
9. Uncertain in-flight phase becomes interrupted when resume cannot be proven.
10. Reconciliation is idempotent when run twice.
11. Legacy records without lease fields normalize safely.
12. Tenant boundaries are preserved.
13. Recovery failure is observable and does not corrupt terminal history.

## Validation
Doctor once; focused tests; Ruff changed files. Because persistence + async lifecycle/recovery change, run RAG affected-service suite once near completion. Mypy only if relevant typed contracts are in normal scope.

## Manual gate
With a disposable Smoke benchmark:
1. start run;
2. let at least one phase finish;
3. restart RAG container/process;
4. reopen Benchmark Center;
5. verify completed phase was not rerun;
6. verify no duplicate phase eval run exists;
7. verify benchmark resumes safely or is explicitly interrupted;
8. verify it never remains falsely running indefinitely.

Also restart with an already completed benchmark and verify no change.

## Final report
Return lease schema, atomic ownership approach, startup reconciliation algorithm, resume-vs-interrupt rules, duplicate-prevention evidence, test results, and manual checks remaining. Do not commit or push.
