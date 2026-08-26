# Current Project State

Keep this file compact and update only when major project state changes.

## Architecture
RAGForge uses:
- Gateway for browser-facing REST/auth/service façade.
- RAG for Regular/Extended conversation orchestration and eval.
- Files for upload/ingestion/review/audit.
- Embedding for extraction/embedding workloads.
- Vector DB for Qdrant operations.
- Memory for chat history/long-term memory and memory-agent workflows.
- LLM Agent for generation/evaluation model operations.
- RabbitMQ for RPC; Kafka for durable async workflow/events.
- MongoDB, Qdrant, self-hosted vLLM and Prometheus.

## Eval / benchmark
- Golden-set IR metrics exist.
- Eval candidate depth is separate from production context K in the last audited main snapshot.
- Citation/claim evaluation and Metrics UI exist.
- Per-item retrieval diagnostics (candidates/ranks/provenance) are attached to eval item rows by `retrieval_trace.py`, collected opt-in so user turns are unaffected.
- Stage failure attribution is deterministic (`failure_attribution.py`): every eval/benchmark item carries one category plus evidence, counted into each run's `results.failure_attribution`; insufficient evidence is `unclassified`, never an LLM guess.

## High-value tracked areas
See task files and registries for exact status:
- Pass2 global candidate ranking.
- Agent mutation policy/evals.
- Canonical turn/outbox.
- Async RAG persistence/checkpoint retention.
- Frontend token-stream batching.
- Container/runtime hardening.
- Automated Benchmark Center.

## Rule
This summary is not proof. Verify current source and generated index before changing code.
