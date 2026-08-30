# MEMORY-V2-02 — Consolidation, conflict handling, and index reconciliation

**Order:** 33  
**Phase:** 5 Memory V2  
**Priority:** P0  
**Branch:** `feat/memory-v2-lifecycle`  
**Depends on:** `MEMORY-V2-01`

## Goal

Add deterministic production-grade consolidation, temporal conflict handling, and reconciliation between canonical memory persistence and the vector index.

The system must avoid accumulating duplicated, stale, contradictory, or half-indexed memories while preserving useful historical context where appropriate.

## Primary scope

- semantic duplicate detection
- memory consolidation/update semantics
- temporal supersession
- conflict handling
- canonical DB ↔ vector index reconciliation
- idempotency
- retry/recovery
- deletion correctness
- reconciliation observability

## Required behavior

### 1. Semantic duplicate handling

For candidate memories that are effectively the same fact:

- detect near-duplicate semantic content
- avoid creating redundant active memories
- update/merge according to deterministic policy
- preserve source/provenance
- do not merge unrelated facts merely because embeddings are similar

Use bounded candidate comparison.

### 2. Temporal updates

Support cases such as:

Old:
`The project deploys to GCP.`

New:
`For the new environment, deployment moved to AWS.`

The system must be able to distinguish:

- replacement/supersession
- scope-specific coexistence
- historical fact
- true contradiction

Do not blindly delete all older related memories.

### 3. Conflict policy

Define explicit outcomes such as:

- keep existing
- create new
- supersede existing
- merge
- preserve both with temporal/scope distinction
- reject ambiguous update for later policy handling

Exact enum names may follow current architecture.

The policy must be deterministic at this layer. LLM-based reasoning belongs to MEMORY-AGENT-01 unless already required by an existing contract.

### 4. Index reconciliation

Provide a bounded reconciliation path for:

- DB memory exists, vector missing
- vector exists, DB memory missing
- stale vector revision
- deleted/superseded memory still retrievable
- duplicate vectors for one canonical memory

Reconciliation must be:

- tenant-safe
- idempotent
- observable
- resumable/bounded

Do not perform destructive global rebuilds by default.

### 5. Idempotency

Repeated delivery/retry of the same create/update/delete event must not produce:

- duplicate canonical records
- duplicate vectors
- divergent revisions
- resurrected deleted memory

### 6. Failure recovery

Test partial-failure sequences such as:

DB write succeeds → vector upsert fails

vector delete succeeds → DB update fails

service restarts during reconciliation

retry arrives after original operation completed

The resulting state must either be correct immediately or explicitly marked for reconciliation.

### 7. Retrieval semantics

After consolidation:

- current queries should prefer active/current memories
- deleted/superseded entries should not contaminate normal retrieval
- historical retrieval, if supported, must remain explicit

### 8. Observability

Expose reconciliation evidence:

- drift detected
- repaired
- failed
- duplicates merged
- conflicts resolved by class
- retries/idempotent no-op

No memory text in metric labels.

## Non-goals

- No full autonomous Memory Agent.
- No broad prompt work.
- No document RAG changes.
- No final large memory benchmark.
- No frontend redesign.

## Validation

Required:

- focused semantic dedupe tests
- conflict/supersession tests
- temporal-scope tests
- idempotency tests
- DB/vector drift tests
- reconciliation tests
- restart/retry tests where existing harness supports them
- tenant/user isolation regression tests
- memory affected suite
- Ruff
- canonical mypy if applicable
- Compose/build if runtime changed
- diff-check

## Measurement

Create a deterministic scenario pack with at least:

- exact duplicates
- semantic duplicates
- valid coexistence
- explicit contradictions
- temporal updates
- scoped updates

Report:

- duplicate suppression accuracy
- conflict/supersession correctness
- reconciliation success count
- unresolved count
- leakage count
- reconciliation latency where meaningful

## Final report

Return:

### MEMORY-V2-02 CLOSEOUT

Consolidation:
- exact duplicate policy
- semantic duplicate policy
- candidate bound

Conflict handling:
- outcomes
- temporal semantics
- scope semantics

Reconciliation:
- drift classes handled
- repair behavior
- idempotency
- restart/retry behavior

Validation:
- focused
- affected
- integration
- Ruff
- mypy
- Compose/build
- diff-check

Measurement:
- scenarios
- duplicate correctness
- conflict correctness
- reconciliation success
- unresolved
- leakage

Remaining debt:
- deferred agent-policy decisions

Final status:
`COMPLETE` or `BLOCKED`

## Execution rules

- Current source wins.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit or push unless explicitly requested.
- Use focused tests while iterating.
- Do not widen scope into agent autonomy.
- After final source edit: source freeze.
- STOP after MEMORY-V2-02.
