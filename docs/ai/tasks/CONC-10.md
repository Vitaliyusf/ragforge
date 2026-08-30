# CONC-10 — Make process ownership explicit and enable safe worker scale-out

**Phase:** Runtime scale  
**Priority:** P1  
**Branch:** `perf/process-scaleout`  
**Depends on:** `CONC-03`, `CONC-04`, `CONC-05`, `CONC-06`, `CONC-07`, `CONC-09`

## Goal

Move from accidental "one Uvicorn process per service" constraints to an explicit service scaling matrix.

## Audit evidence

All backend Dockerfiles currently start one Uvicorn worker.

Blindly setting `--workers N` is unsafe because services contain process-local resources such as:

- Kafka consumers;
- Rabbit consumers;
- Socket.IO connection state;
- RAG eval/benchmark background tasks;
- local semaphores/task registries;
- SentenceTransformer/CrossEncoder model instances;
- local caches and circuit breakers.

## Required deliverable: service scaling matrix

For each service classify:

```text
Gateway
RAG
LLM Agent
Embedding
Memory
Files
Vector DB
```

with:

- stateless HTTP safe? yes/no;
- process-local state;
- background consumer ownership;
- model ownership;
- broker consumer-group behavior;
- safe workers per replica;
- safe replicas;
- required shared state before scaling;
- resource multiplier.

## Required implementation

Only implement worker/replica increases proven safe.

Examples of possible outcomes:

- Gateway may support >1 worker after process-local limits are understood.
- Embedding may intentionally remain one model process per device.
- RAG may remain one Socket.IO process until a shared Socket.IO manager/sticky routing is justified.
- Kafka worker roles may scale independently from HTTP roles.
- LLM Agent may use multiple queue consumers but must not multiply the global vLLM budget accidentally.

If separating API and worker roles is the cleanest solution, add explicit role flags/entrypoints rather than forking application code.

## Metrics/config

Expose worker/replica identity only as bounded diagnostic metadata, not high-cardinality metric labels.

Document CPU/RAM/model-memory cost per added process.

## Load validation

For every worker-count change compare:
- throughput;
- p95/p99;
- error rate;
- RSS;
- broker duplicate/rebalance behavior;
- model memory;
- Socket.IO correctness where applicable.

## Non-goals

- no Kubernetes manifests in this task;
- no distributed scheduler;
- no Redis solely to permit a second worker unless the measured benefit justifies a separate decision.
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
