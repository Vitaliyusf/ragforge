# Engineering Rules

## Python
- Target Python 3.12 until explicitly upgraded.
- Use modern typing (`dict[str, T]`, `X | None`) in newly touched code where project tooling supports it.
- Pydantic models belong at transport/config boundaries.
- Prefer `Protocol` for structural interfaces; use ABC inheritance only when behavior/lifecycle inheritance is meaningful.
- Keep pure calculations as pure functions. Do not create "manager" classes around stateless functions.
- Use dataclasses/classes for stateful runtime, policy, repository, unit-of-work, resource/lifecycle concerns.
- Avoid "utils.py" growth; place behavior near its domain.
- No import-time network/database connections.

## FastAPI / async
- App/lifecycle resources should be created and closed in lifespan.
- Prefer app/runtime-owned clients over module globals.
- Never call `time.sleep()` on an async request path.
- Avoid synchronous Mongo/HTTP calls directly in async hot paths; use async APIs or intentional bounded offload.
- Bound fan-out with semaphore/config. Never add unbounded `gather`.
- Cancellation/timeouts should propagate instead of leaving zombie work where possible.
- Route handlers should validate/authorize/dispatch; business logic belongs in services.

## MongoDB
- Every tenant-domain query/write must include trusted tenant/owner scope.
- New query patterns need an index review.
- Prefer atomic updates/unique constraints for idempotency.
- Never fake transaction fallback after caller code has already executed.
- TTL retention should be explicit for temporary metrics/checkpoint/eval artifacts.
- Avoid N+1 lookups where a scoped bulk query can resolve the same data.

## Kafka / RabbitMQ
- RabbitMQ = RPC; Kafka = durable pipeline/events unless a task explicitly changes this.
- For critical Kafka work target at-least-once + idempotent consumers.
- Do not claim exactly-once without end-to-end evidence.
- Delivery/offset semantics must be explicit.
- Event envelopes should be versioned and shared rather than copied per service.
- Retry policies must classify retryable vs non-retryable errors and avoid infinite loops.

## RAG / AI
- Keep production retrieval logic free of golden-set expected labels.
- Candidate lineage may contain IDs/ranks/scores/provenance; private text must be bounded/admin-only.
- Distinguish candidate generation, ranking/reranking, context selection and answer generation.
- Do not name a sort/dedupe operation a learned reranker.
- `null` = unmeasured; denominator counts accompany rates.
- LLM judges are judge-evaluated proxies, not objective truth.
- Version dataset/config/model/prompt metadata for reproducibility.

## React / Next.js
- Separate server state, local UI state and high-frequency streaming state.
- Do not update a large Context/reducer for every token if buffering can reduce renders.
- Polling must stop when unnecessary and pause while hidden where practical.
- AbortSignal must reach `fetch`; ignoring a stale response is not cancellation.
- Prefer focused components/hooks over large page components with many responsibilities.
- Avoid duplicate source of truth for the same domain value.
- Use stable domain IDs as keys.
- Dynamic imports are useful only when they reduce real initial work/bundle cost.
- Avoid new packages when existing primitives/CSS suffice.

## Performance
- Measure before/after on the same dataset/config/hardware.
- Report sample count, p50/p95/p99 where meaningful, errors, throughput and resource pressure.
- Optimize tail latency and contention, not only mean latency.
- Do not merge a performance optimization whose correctness/quality regresses beyond accepted tolerance without explicit approval.

## Refactoring
- Behavior-neutral refactors and behavior changes should be separate branches when possible.
- Delete compatibility/dead code only after repo-wide reference verification and tests.
- Prefer fewer code paths over permanent "legacy + v2" dual implementations.

## 1. Complexity ratchet
Line count is a review signal, not architecture.

- New production file >400 lines: justify why it is one cohesive responsibility.
- New production file >600 lines: do not create it without explicit task acceptance.
- Touched existing production file >500 lines: inspect whether the concern changed by the task can be extracted safely.
- Touched existing production file >700 lines: it should not materially grow unless the task explicitly explains why extraction would worsen design.
- New/touched function >80 lines: inspect for a cohesive extraction.
- New function >150 lines: requires explicit justification.
- Tests, generated files, migrations and declarative data may be exceptions.
- Never split code merely to satisfy a numeric limit.

## 2. Local refactor budget
Every task may perform behavior-neutral cleanup in its already-touched scope.

Allowed:
- extract the exact concern being changed from a hotspot;
- delete replaced/dead compatibility code after reference proof;
- collapse duplicate branches;
- rename misleading symbols;
- remove stale narrative comments;
- move one responsibility to a domain-owned module;
- simplify lifecycle/dependency ownership.

Default budget:
- at most 2 cohesive new production modules unless task scope explicitly requires more;
- prefer code deletion or neutral movement over parallel implementations.

Not allowed:
- unrelated repo-wide cleanup;
- architecture rewrite;
- speculative generic framework;
- multiple new abstractions “for future flexibility.”

## 3. New-file gate
Before creating a production file:
1. Search for the existing capability/symbol/domain owner.
2. State the new file's responsibility in one sentence.
3. Prefer extending/replacing the canonical owner.
4. Give the file one clear domain responsibility and owner.
5. Reject dumping-ground names such as `utils`, `utils2`, `helpers`, `manager`, `misc`, `common`, `common2`, `v2`.
6. Prefer domain names such as `context_assembler.py`, `checkpoint_policy.py`, `memory_reconciliation.py`.

## 4. One authoritative implementation per capability
Each capability has one authoritative implementation. Before adding another path for:
- chat execution;
- embedding handling;
- extraction/chunking;
- vector backend;
- config mutation;
- LLM provider/control;
- tracing exporter;

search references, capability records, symbols and direct callers. Extend or replace the
canonical owner; do not create a second implementation unless the task explicitly requires
a separate supported capability and names its domain owner.

## 5. Compatibility rule
Default: migrate and delete.

Temporary compatibility is allowed only when:
- a real supported caller still exists;
- a concrete removal condition and tracking task are recorded;
- both paths cannot silently diverge.

Migrate supported callers and delete the old path as soon as the removal condition is met.
Do not create permanent `legacy + v2` architecture.

## 6. Configuration honesty
A configuration option must represent real, implemented effective behavior.

Unsupported updates fail explicitly.
Do not preserve flags for nonexistent hybrid/reranker/provider/runtime behavior.

## 7. Comment policy
Keep comments for:
- security invariants;
- recovery/checkpoint invariants;
- protocol and delivery semantics;
- concurrency/cancellation ordering;
- benchmark/eval semantics;
- non-obvious performance trade-offs.

Delete:
- syntax narration;
- comments that simply restate names;
- historical incident stories better placed in ADR/task history.
