# MEMORY-AGENT-01 — Harden the Memory Agent policy and typed LLM control flow

**Order:** 34  
**Phase:** 5 Memory V2  
**Priority:** P0  
**Branch:** `feat/memory-agent-hardening`  
**Depends on:** `MEMORY-V2-02`, `LLM-CTRL-01`

## Goal

Turn the Memory Agent into a bounded, typed, observable policy layer over the corrected Memory V2 substrate.

The agent must make explicit, validated decisions about whether information should become long-term memory and what lifecycle action should occur, without owning persistence/index mechanics directly.

## Primary scope

- memory candidate extraction
- typed LLM operations
- memory-worthiness policy
- lifecycle action selection
- conflict/consolidation decision support
- bounded tool protocol
- business validation
- retries/fallbacks
- provenance
- token/latency observability
- tenant-safe memory tool access

## Required behavior

### 1. Agent boundary

The Memory Agent is a policy/orchestration layer.

It may decide:

- ignore
- create
- update
- supersede
- merge suggestion
- delete when explicitly authorized by product semantics

It must not directly bypass canonical MEMORY-V2 service ownership.

### 2. Typed LLM operations

Use the existing LLM control-plane conventions from `LLM-CTRL-01`.

Operations should be explicit and schema-driven, such as:

- extract memory candidates
- classify memory type
- determine memory worthiness
- compare candidate with existing memory
- choose lifecycle action
- summarize/normalize memory text where needed

Do not use scattered free-form JSON parsing.

### 3. Business-valid output

Valid JSON is not enough.

Validate:

- allowed action
- required IDs for update/supersede/delete
- tenant/user scope
- candidate text constraints
- confidence/decision fields if used
- no action referring to memory outside the bounded candidate set

Reject structurally valid but business-invalid decisions.

### 4. Bounded context/tools

The agent must receive only bounded memory candidates and bounded conversation context.

No unbounded retrieval.

No arbitrary tool access.

All memory mutations go through typed canonical service methods.

### 5. Memory-worthiness policy

Avoid storing:

- greetings
- transient filler
- one-off irrelevant chatter
- duplicated facts already active
- low-value assistant-generated text
- unsupported inferred personal facts

Prefer durable information explicitly supplied by the user or product-approved sources.

Policy must follow existing product/privacy contracts.

### 6. Conflict behavior

The agent may help distinguish:

- correction
- temporal update
- scope-specific difference
- duplicate/paraphrase
- unrelated fact

But final persistence action must still pass deterministic service validation.

### 7. Failure behavior

If the LLM:

- times out
- returns invalid structured output
- returns business-invalid action
- is unavailable

the system must degrade safely.

Default degradation should avoid destructive mutation.

Do not delete/supersede memory on an unvalidated LLM response.

### 8. Provenance

Record:

- operation type
- model
- prompt version
- schema version/hash where repository supports it
- structured-output transport
- outcome
- retry/fallback
- latency/tokens

Never expose private memory content in metric labels.

### 9. Security/isolation

Agent tools must inherit and validate:

- tenant_id
- user_id
- role/scope

The LLM must never be trusted to choose authorization scope.

### 10. Determinism around destructive actions

Delete/supersede actions require deterministic validation.

A model suggestion alone is not sufficient authority.

## Non-goals

- No broad RAG redesign.
- No model upgrade/tuning unless concretely required by the task.
- No autonomous general-purpose agent framework.
- No unrestricted tools.
- No final 10K corpus benchmark.
- No CrossEncoder work.

## Validation

Required:

- candidate extraction tests
- typed schema tests
- business validation tests
- no-memory cases
- duplicate cases
- update/supersede cases
- conflicting-memory cases
- LLM timeout/error/invalid JSON/invalid business action
- tenant/user isolation
- destructive-action safety
- affected memory suite
- affected LLM control-plane tests
- Ruff
- canonical mypy if applicable
- Compose/build if runtime changed
- diff-check

## Measurement

Create an initial deterministic agent scenario suite.

At minimum include:

- durable preference
- transient chatter
- project fact
- duplicate fact
- corrected fact
- temporal update
- scope-specific fact
- contradiction
- deletion request
- irrelevant assistant output
- cross-tenant adversarial case

Report:

- correct no-op rate
- correct create rate
- correct update/supersede rate
- unsafe destructive action count
- tenant leakage count
- structured-output failure rate
- mean/p50/p95 LLM action latency where sample size supports it
- token usage

## Final report

Return:

### MEMORY-AGENT-01 CLOSEOUT

Agent boundary:
- canonical tools
- allowed actions
- bounded inputs

LLM control:
- model
- operations
- prompt versions
- schemas
- structured-output transport

Validation:
- schema
- business validation
- safe fallback
- destructive-action protection
- isolation

Measurement:
- scenarios
- correct actions
- incorrect actions
- no-op correctness
- unsafe mutations
- latency
- tokens

Observability:
- metrics
- provenance

Refactor:
- obsolete agent/handler paths removed
- production files added/deleted
- dependencies

Final status:
`COMPLETE` or `BLOCKED`

## Execution rules

- Current source wins.
- Preserve unrelated work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not bypass the canonical Memory V2 service.
- Do not expand into a general agent framework.
- Use typed control-plane patterns already established by LLM-CTRL-01.
- Source freeze after final source edit.
- STOP after MEMORY-AGENT-01.
