# MEMORY-V2-01 — Rebuild memory architecture and semantic correctness

**Order:** 32  
**Phase:** 5 Memory V2  
**Priority:** P0  
**Branch:** `feat/memory-v2-architecture`  
**Depends on:** `RAG-04`

## Goal

Rebuild the current memory subsystem into one coherent, production-oriented architecture with explicit ownership, real semantic retrieval, deterministic lifecycle semantics, tenant/user isolation, and measurable correctness.

The task is not to add more memory features. It is to make the existing memory capability structurally correct and trustworthy before agent autonomy is expanded.

## Primary scope

- memory service ownership and boundaries
- memory persistence model
- memory vectorization / semantic search
- query and retrieval path
- lifecycle/state semantics
- duplicate handling foundations
- tenant/user isolation
- provenance and observability
- removal of obvious legacy/parallel memory paths in touched scope

## Required behavior

### 1. Establish canonical memory ownership

There must be one authoritative path for:

- memory creation
- memory persistence
- embedding/vector indexing
- retrieval
- update/supersession
- deletion

Do not keep two active implementations that can diverge.

If current code contains overlapping ownership between files such as:

- `memory_service.py`
- `memory_qdrant_service.py`
- `memory_agent.py`
- `memory_handler_service.py`

identify the canonical owner for each responsibility and remove/deprecate obsolete touched paths rather than adding wrappers around them.

### 2. Real semantic representation

Memory retrieval must not depend on weak placeholder hashing or non-semantic vectorization when the production repository already has an embedding service/model.

Use the canonical production embedding path where architecturally appropriate.

Requirements:

- same embedding dimensionality expected by the memory vector store
- explicit model/version provenance
- deterministic error behavior
- bounded request size
- no silent fallback to random/non-semantic vectors
- no direct external model download in production runtime unless already part of canonical runtime ownership

### 3. Explicit memory model

Define the smallest production-grade memory record that supports lifecycle and retrieval.

At minimum preserve/introduce equivalent semantics for:

- memory_id
- tenant_id
- user_id / owner scope
- canonical text/content
- memory type/category where already supported
- source/provenance
- created_at
- updated_at
- status
- version/revision where needed
- supersedes / superseded_by when applicable
- vector/index synchronization state if needed
- stable metadata required for filtering

Do not create speculative metadata with no consumer.

### 4. Memory lifecycle

Memory state must be explicit.

Support a coherent lifecycle equivalent to:

`active -> updated/superseded -> archived/deleted`

Exact names may follow current contracts.

Required semantics:

- an updated fact must not leave two equally-authoritative active memories
- deletion must remove or tombstone both canonical persistence and retrieval representation according to repository contracts
- retrieval must not return deleted/superseded memories as current facts unless historical retrieval is explicitly requested
- lifecycle transitions must be deterministic and testable

### 5. Retrieval correctness

The memory query path must:

- use semantic retrieval
- apply tenant isolation
- apply user/owner isolation
- exclude inactive/deleted memory
- remain bounded
- return deterministic ordering for ties
- preserve score/provenance useful for diagnostics
- expose truthful empty/failure behavior

Do not mix document-RAG retrieval semantics into memory unless the current architecture explicitly shares a primitive.

### 6. Tenant and user isolation

This is P0.

Prove:

- Tenant A cannot retrieve Tenant B memory
- User A cannot retrieve User B private memory
- overlapping identifiers/content do not bypass filters
- delete/update operations cannot affect another tenant/user

Any cross-tenant or cross-user leakage is a blocker.

### 7. Duplicate foundations

Implement or establish the canonical boundary required for later consolidation.

At minimum:

- avoid exact duplicate active memories
- use deterministic identity/content normalization where appropriate
- expose enough information for MEMORY-V2-02 to perform semantic dedupe/conflict consolidation

Do not build a large autonomous merge policy in this task unless current code already requires it for correctness.

### 8. Failure semantics

Define explicit behavior when:

- embedding fails
- vector upsert fails
- canonical DB write fails
- vector query fails
- delete partially fails

Do not silently report success when one authoritative side failed.

Where atomic cross-system transactions are impossible, use explicit reconciliation state or deterministic recovery semantics.

### 9. Observability

Expose truthful memory-operation metrics where repository conventions support them.

Useful dimensions include:

- operation
- status
- latency
- result count
- failure reason class

Do not emit user content or sensitive memory text in metrics/log labels.

### 10. Provenance

Record enough runtime/config evidence to answer:

- which embedding model produced memory vectors
- which vector collection/index is active
- which memory implementation/path is active
- which filters/scopes are applied

## Local refactor budget

This task may perform behavior-neutral cleanup in code it already needs to touch.

- Extract cohesive ownership from hotspot files when it materially improves the memory boundary.
- Prefer deleting obsolete touched paths over keeping compatibility wrappers.
- Do not create generic `utils`, `helpers`, `manager`, `common2`, `misc`, or duplicate `v2` runtime modules.
- Avoid broad repository cleanup unrelated to memory.
- Preserve public contracts unless a current contract is concretely wrong and migration is included in scope.

## Non-goals

- No autonomous Memory Agent policy redesign yet.
- No LLM-driven conflict resolution policy beyond what correctness requires.
- No large memory benchmark yet; only build the benchmark foundation/hooks.
- No document RAG redesign.
- No CrossEncoder optimization.
- No ingestion redesign.
- No frontend redesign.

## Validation

Run only authoritative affected lanes.

Required minimum:

- focused memory service tests
- memory retrieval/query tests
- tenant/user isolation tests
- lifecycle/delete/update tests
- embedding/vector integration tests for affected path
- memory service affected suite
- shared affected tests if shared code changed
- gateway affected tests if API contracts changed
- Ruff on changed Python
- canonical mypy if authoritative scope is touched
- Docker Compose config
- memory service build/startup if runtime/dependencies changed
- `git diff --check`

Use real embedding/vector integration where existing test infrastructure supports it.

## Measurement

Capture a small deterministic memory retrieval check sufficient to prove the new architecture works before moving on.

At minimum report:

- number of test memories
- retrieval Hit@1 / Recall@K where labels exist
- exact duplicate rejection/dedupe behavior
- tenant leakage count
- user leakage count
- retrieval latency sample
- embedding/model provenance

Do not overstate this as the final memory benchmark.

## Final report

Return:

### MEMORY-V2-01 CLOSEOUT

Architecture:
- canonical memory owner
- canonical persistence
- vector/index owner
- embedding model
- vector size
- retrieval path
- lifecycle states

Correctness:
- create
- retrieve
- update
- supersede
- delete
- exact duplicate behavior

Isolation:
- tenant leakage
- user leakage

Failure semantics:
- DB failure
- embedding failure
- vector failure
- partial-write handling

Observability:
- metrics added/changed
- provenance

Refactor:
- production files added
- production files deleted
- obsolete paths removed
- hotspot before/after where relevant
- dependencies added/removed

Validation:
- focused
- affected suite
- integration
- Ruff
- mypy
- Compose
- build/startup
- diff-check

Measurement:
- retrieval quality sample
- latency
- leakage count

Remaining debt:
- items intentionally deferred to MEMORY-V2-02 / MEMORY-AGENT-01

Final status:
`COMPLETE` or `BLOCKED`

## Execution rules

- Current source wins over stale assumptions.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit or push unless explicitly requested.
- Do not run generic `doctor` as a prerequisite.
- Do not repair `.venv` as normal task work.
- Use canonical runtime/tooling if local Python is unsuitable.
- Bootstrap Repo Brain exactly as repository policy requires.
- Explore memory ownership first; do not perform repo-wide discovery unless needed.
- Iterate with focused tests.
- Run affected service suite once near completion.
- After final source edit: source freeze.
- Do not reopen completed unrelated tasks for speculative cleanup.
- STOP after MEMORY-V2-01.
- Do not automatically start MEMORY-V2-02.
