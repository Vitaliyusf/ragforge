# CONC-01 — Multiplex RabbitMQ RPC and reuse transport resources

**Phase:** Performance / concurrency foundation  
**Priority:** P0  
**Branch:** `perf/rpc-multiplexing`  
**Depends on:** `CONC-00`

## Goal

Remove per-request RabbitMQ connection/channel/reply-queue churn and establish one bounded, reusable RPC transport contract.

## Audit evidence

Current hot paths include:

- `backend/gateway/app/core/rpc_client.py`: shared connection, but a new channel, exchange declaration and exclusive reply queue per request.
- `backend/rag/app/messaging/rpc_client.py`: same pattern; streaming adds another exclusive queue.
- `backend/rag/app/messaging/rpc_client.py::publish`: opens a channel/exchange per fire-and-forget publish.
- `backend/memory/app/services/memory_embedding_client.py`: opens a fresh robust RabbitMQ connection per embedding call.
- `backend/memory/app/services/chat_exit_service.py`: opens a fresh connection/request-scoped reply queue for typed LLM calls.

## Required design

Implement a reusable RPC client with:

- one robust connection per process;
- long-lived publish channel(s);
- one long-lived exclusive reply queue per client/process where practical;
- correlation-id → `Future` registry;
- timeout cleanup;
- cancellation cleanup;
- late-reply handling;
- bounded maximum in-flight RPCs;
- deterministic shutdown that fails outstanding futures;
- reconnect behavior;
- safe auth/context propagation;
- stream-event routing for RAG without losing event order.

Do not multiplex unrelated tenant/user replies without verifying correlation isolation.

## Streaming

For RAG streaming:

- preserve ordered stream events;
- final reply and stream drain semantics remain explicit;
- a timed-out/cancelled request removes its routing state;
- a late stream event cannot attach to a later request.

Use either:
- one multiplexed stream queue with request/correlation routing; or
- a bounded pool of stream resources.

Do not create an exclusive queue per token/event.

## Memory migration

Replace `asyncio.run()` + per-call `connect_robust()` paths with the shared runtime transport/bridge.

Memory's synchronous domain layer may call a thread-safe bridge if necessary, but the bridge must schedule work onto the service loop without constructing a new connection per call.

## Measurements

Compare before/after:

- RPC p50/p95/p99;
- channel creation count;
- queue declaration count;
- connection count;
- max in-flight;
- timeout rate;
- reconnect recovery;
- throughput at concurrency 1/4/8/16/32.

## Tests

Required:

- 100+ concurrent correlated replies map to the correct caller;
- out-of-order broker replies remain correctly correlated;
- timeout removes waiter;
- cancellation removes waiter;
- late reply is ignored safely;
- reconnect preserves future requests;
- shutdown resolves/fails outstanding callers;
- streaming order remains correct;
- tenant/user auth context is preserved;
- no reply cross-talk.

## Non-goals

- no model tuning;
- no Kafka redesign;
- no Uvicorn worker increase;
- no business-contract changes.
## Validation — MINIMAL

Follow `CONC-VALIDATION-POLICY.md`.

For this task run only:

- the smallest focused regression test(s) that prove the changed behavior;
- Ruff on changed Python files;
- `git diff --check`.

Do **not** run a full service suite, repository suite, broad mypy, Docker rebuild, or load benchmark unless this task explicitly owns that measurement.

If the task includes a benchmark section, run only the smallest benchmark needed to prove this task's own performance claim. The full load campaign belongs to `CONC-99`.

## Execution rules

- Current source wins.
- Preserve unrelated dirty/untracked work.
- Never reset/stash/revert/clean.
- No commit/push unless explicitly requested.
- Do not repair `.venv`.
- Use isolated Python 3.12 fallback only if needed.
- Once the focused regression is green, STOP.
