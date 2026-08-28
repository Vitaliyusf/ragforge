# GEN-04 — Benchmark execution profiles and expensive-phase control

**Branch:** `feat/benchmark-run-profiles`

## Goal

Stop treating every benchmark run as "run every expensive phase".

Add explicit benchmark profiles so routine quality checks do not automatically execute Extended E2E across the entire Full240 dataset.

## Motivation

A Full240 diagnostic run currently spends the overwhelming majority of wall time in E2E LLM phases.

Retrieval is cheap.
Regular E2E is expensive.
Extended E2E is even more expensive and does not currently show a clear enough quality win to justify always running it on all 240 items.

The product should let the user choose what evidence is needed.

## Required profiles

Implement the smallest useful set, conceptually:

### Quick Retrieval

```text
retrieval_base
```

### Smoke Quality

```text
regular E2E
```

intended for Smoke30.

### Full Quality

```text
retrieval_base
regular E2E
```

intended for Full240 / Baseline quality.

### Extended Comparison

```text
regular E2E
extended E2E
```

intended for targeted diagnostic subsets.

### Full Diagnostic — Expensive

```text
retrieval_base
regular E2E
extended E2E
```

Keep `retrieval_extended` represented as unsupported if that remains the truthful implementation.

Use names consistent with existing UI/product vocabulary.

## Backend contract

Persist the selected profile in the benchmark run.

The benchmark manifest/export must record:

```text
requested profile
actual executable phases
unsupported phases
skipped phases
```

Historical runs must remain interpretable.

Do not infer profile from phases after the fact when it was explicitly selected.

## UI

Before Start, show:

```text
Profile
Executable phases
Dataset item count
Expensive / normal warning
```

Example:

```text
Full Quality
Retrieval baseline + Regular E2E
240 items
```

For `Full Diagnostic`, show a clear warning:

```text
Expensive: runs Regular and Extended E2E over the selected dataset.
```

Do not invent a precise ETA unless enough historical evidence exists.

A rough label such as:

```text
Fast
Moderate
Expensive
```

is acceptable if based on phase structure, not fake duration math.

## Default behavior

For Full240 quality work, preferred default should be:

```text
Full Quality
```

not full Regular+Extended diagnostic.

Do not change historical runs.

## Non-goals

Do not:

- optimize LLM execution itself;
- change phase scoring;
- change retrieval;
- implement BMARK-14 comparison;
- remove Extended mode;
- run Full240 during implementation.

## Required tests

Backend:

1. each profile maps to the correct executable phases.
2. unsupported phases remain unsupported.
3. profile persists on benchmark run.
4. export records requested/actual phases.
5. legacy benchmark without profile remains readable.
6. manually specified invalid profile is rejected.

Frontend:

7. profile selector renders.
8. selected profile drives start request.
9. expensive profile warning renders.
10. Full Quality does not include Extended E2E.
11. current/history view shows profile where useful.

## Validation

Focused backend/frontend tests.
Frontend production build:

```powershell
cd frontend
npm run build
```

Run RAG affected suite only if backend orchestration contract changes materially.

## Manual acceptance

Use Smoke30 and confirm each profile starts exactly the expected phases.

Do not run Full240 merely to validate routing.

After GEN-01..03 are stable, run one **Full240 Full Quality** benchmark as the next large before/after checkpoint.

## Final report

Return:

1. profile definitions;
2. backend phase mapping;
3. UI behavior;
4. default-selection decision;
5. tests/build;
6. manual profile verification still required.

Do not commit or push.
