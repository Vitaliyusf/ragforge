# Symptom / Request → First Search Direction

| Request / symptom | Start here | Then inspect |
|---|---|---|
| RAG answer wrong | `backend/rag/app/services/conversation_graph.py` | backend client, retrieval diagnostics, eval result |
| Relevant chunk missing | RAG retrieval + Qdrant implementation | embedding config/model, chunk metadata |
| Pass2 did not help | graph Pass1/Pass2/merge/context symbols | diagnostic trace/eval |
| New retrieval metric | `retrieval_metrics.py`, `metrics_facts.py` | `metrics_query.py`, Gateway MetricsService, Metrics UI |
| Benchmark/eval feature | `eval_runner.py`, `eval_store.py` | Gateway eval routes, Metrics/Eval frontend |
| File metadata/status | Files service/repository | Gateway Files façade, `fileService.js` |
| Ingestion stuck | `file_ingestion_graph.py` | Kafka consumer, embedding job, vector worker |
| Embedding/query vector issue | embedding service/model | RAG backend client, Vector search |
| Qdrant issue | `vector_db/app/db/implementations/qdrant.py` | vector service/schema/filters |
| Chat history mismatch | RAG persist-turn + Memory persistence | frontend ChatContext browser-side writes |
| Memory agent wrong mutation | `memory/app/agent/memory_agent.py` | policy/tool executor/tasks AGENT-* |
| LLM output/judge issue | llm_agent prompts/implementation | RAG generation/evaluation nodes |
| Metrics panel wrong | frontend metrics component | metricsService, Gateway MetricsService, source metric |
| Request does not cancel | `frontend/src/lib/http/client.js` | polling hook caller |
| Frontend slow while streaming | ChatContext/reducer | token handler/message renderer |
| Multi-file upload slow | `useFiles.js` | fileService/Gateway/Files backend |
| Kafka duplicate/loss | `backend/shared/kafka_base.py` | consumer idempotency/durable-write ordering |
| RabbitMQ latency/error | Gateway/shared RPC client | target service consumer |
| Tenant leak concern | auth scope + repository/vector filters | authorization tests |
| Docker image large | Dockerfile + requirements | optional/test deps, Next standalone |
