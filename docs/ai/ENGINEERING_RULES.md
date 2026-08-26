# Engineering Rules

## Python
- Target Python 3.11 until explicitly upgraded.
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
