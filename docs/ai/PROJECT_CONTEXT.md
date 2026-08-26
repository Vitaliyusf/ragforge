# RAGForge Project Context

RAGForge is a production-oriented, self-hosted, multi-tenant RAG/AI application.

## Application services
- `gateway` — browser-facing REST gateway, authentication/session, RPC façade, admin metrics/eval routes.
- `rag` — conversation orchestration, Regular/Extended RAG, retrieval, evaluation, citations, checkpoints, eval harness.
- `files` — upload, file metadata, ingestion workflow, review/audit state.
- `embedding` — extraction/embedding pipeline and embedding model execution.
- `vector_db` — Qdrant-backed chunk vector persistence/search.
- `memory` — chat history, long-term memory, memory curation agent.
- `llm_agent` — LLM generation/evaluation abstraction and self-hosted model access.

## Infrastructure
- MongoDB — domain persistence.
- RabbitMQ — synchronous/inter-service RPC.
- Kafka — durable ingestion/event pipeline.
- Qdrant — vector store.
- vLLM — self-hosted LLM serving.
- Prometheus — operational metrics.
- Next.js/React — frontend.
- Caddy — production reverse proxy/TLS.

## Core invariants
- Tenant isolation is mandatory across Mongo, Qdrant, files, traces, eval and exports.
- User/tenant scope originates in trusted server/auth context.
- The browser is not a trusted source of tenant/user identity.
- RabbitMQ and Kafka have different roles; do not merge them casually.
- Evaluation truth is versioned evidence, not an LLM opinion.
- Do not claim hybrid retrieval, learned reranking, fail-closed streaming, exactly-once delivery, or production readiness unless executable behavior and tests support the claim.
- Prefer measurement before optimization.

## RAG concepts
- Regular mode: simpler retrieval/generation path.
- Extended mode: rewrite/decomposition, multi-query retrieval, optional second pass, evaluation/revision path.
- `top_k_documents` is production context depth.
- Eval candidate depth is separate and must be >= the largest Recall@K being reported.
- Existing trace IDs include request/trace/correlation/turn/graph identifiers.
- Existing eval infrastructure should be extended, never duplicated.

## Benchmark philosophy
A change is not "better" because it sounds architecturally cleaner. For quality/performance work use:
baseline → candidate → same dataset/config/hardware → compare → merge/reject.
