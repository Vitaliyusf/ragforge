# BMARK-13D — Immutable benchmark dataset snapshot + durable historical export

**Branch:** `fix/benchmark-immutable-export`

## Goal
Make historical benchmark ZIPs reproducible later even if the live Golden Set is edited or deleted.

## Problem
Current export reconstructs part of the archive from the current dataset at download time. That can make old evidence mutable or impossible to reproduce after dataset changes.

## Scope
- benchmark creation persistence
- immutable canonical/scoring dataset snapshot
- export builder
- backward compatibility
- tenant/security tests

## Required behavior
At benchmark start persist enough immutable dataset evidence to reconstruct exactly what was scored, conceptually:

```text
dataset_snapshot:
  dataset_id
  dataset_name if useful
  dataset_version
  dataset_sha256
  canonical scoring items
```

Do not copy unrelated mutable UI metadata.

For new benchmarks, export must use the immutable benchmark snapshot.

Invariant:

```text
benchmark ran on version N
→ export tomorrow still represents version N
```

even if live dataset becomes N+1 or is deleted.

Preserve existing behavior that deleting a Golden Set does not delete historical runs.

## Legacy compatibility
Existing benchmark documents may lack snapshots. They must remain readable.

Use the safest possible legacy behavior and explicitly mark evidence as legacy/current-dataset-dependent when exact reconstruction cannot be proven. Never silently claim immutable provenance.

## Security invariants
Preserve:
- admin-only access
- tenant scoping
- sanitization/redaction
- `allow_nan=False`
- ZIP/path protections
- export size limits
- no unnecessary raw private context/document content

## Non-goals
- no object storage
- no permanent ZIP binary storage if deterministic reconstruction suffices
- no history UI
- no process restart recovery
- no scoring changes

## Required tests
1. Snapshot captured at benchmark start.
2. Snapshot version/hash matches benchmark identity.
3. Dataset edit does not alter old export.
4. Dataset deletion does not break old export.
5. New exports use snapshot.
6. Legacy benchmark remains readable/exportable where possible.
7. Legacy limitation is explicit.
8. Cross-tenant export denied.
9. Secret sanitization preserved.
10. Strict JSON; no NaN/Infinity.
11. Snapshot excludes unnecessary mutable/private fields.

## Validation
Doctor once; focused store/export tests; Ruff changed files; RAG affected-service suite once near completion. Gateway affected checks only if contract changes.

## Manual gate
With a disposable Golden Set:
1. finish benchmark;
2. record version/hash;
3. download ZIP;
4. edit dataset;
5. download old benchmark again and verify original evidence;
6. delete dataset;
7. verify historical export still works.

## Final report
Return snapshot schema, creation point, export source of truth, legacy behavior, test evidence and remaining manual checks. Do not commit or push.
