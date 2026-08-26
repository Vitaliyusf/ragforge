# Repository Map

Use this as navigation, not as a guarantee that every file still exists. Search current code before editing.

## Root
- `docker-compose.yml` — local stack.
- `docker-compose.prod.yml` — production overlay.
- `.github/workflows/ci.yml` — canonical CI commands.
- `docker/requirements-base.txt` — common Python runtime requirements.
- `mypy.ini` — type-check configuration.
- `README.md` — public documentation; not authoritative over code.

## Gateway
- `backend/gateway/app/main.py` — FastAPI app/lifespan.
- `backend/gateway/app/core/deps.py` — dependency getters.
- `backend/gateway/app/services/metrics_service.py` — metrics/eval gateway aggregation.
- `backend/gateway/app/services/*` — domain façades.
- `backend/gateway/app/rest/*` — HTTP routes.

## RAG
- `backend/rag/app/main.py` — ASGI/RabbitMQ/Socket.IO runtime.
- `backend/rag/app/services/conversation_graph.py` — main RAG graph/orchestration.
- `conversation_backend_client.py` — embedding/vector/memory/LLM RPC client.
- `conversation_persistence.py` — turn/checkpoint persistence.
- `conversation_tracing.py` — tracing wrapper.
- `eval_runner.py` — golden-set execution.
- `eval_store.py` — dataset/run persistence.
- `retrieval_metrics.py` — IR metric pure functions.
- `citation_metrics.py` — citation metrics.
- `metrics_facts.py` / `metrics_query.py` — turn facts and query aggregation.

## Files
- `backend/files/app/main.py` — runtime.
- `backend/files/app/services/file_service.py` — request/service façade.
- `backend/files/app/services/file_ingestion_graph.py` — ingestion orchestration.
- `backend/files/app/db/` — repository and domain mixins.
- `backend/files/app/utils/common.py` — legacy/generic helpers; avoid adding more unrelated helpers here.

## Embedding
- `backend/embedding/app/main.py`
- `backend/embedding/app/services/embedding_job_service.py` — typed embedding jobs.
- `backend/embedding/app/services/embedding_handler.py`
- `backend/embedding/app/services/extraction_handler.py`
- `backend/embedding/app/embedding/` — embedding model interfaces/implementations.
- `backend/embedding/app/extraction/` — extractor interfaces/implementations.

## Vector DB
- `backend/vector_db/app/main.py`
- `backend/vector_db/app/services/vector_service.py`
- `backend/vector_db/app/db/interfaces.py`
- `backend/vector_db/app/db/implementations/qdrant.py`

## Memory
- `backend/memory/app/main.py`
- runtime/application module(s)
- `backend/memory/app/agent/memory_agent.py`
- memory/chat repositories/services.

## Shared
- `backend/shared/` — auth, metrics, retry, DLQ, Kafka base, errors, logging and cross-service infrastructure.
New cross-service primitives belong here only when at least two services truly share the same contract.

## Frontend
- `frontend/src/components/Providers.jsx`
- `frontend/src/components/layout/TabbedPageLayout.jsx`
- `frontend/src/features/chat/`
- `frontend/src/features/files/`
- `frontend/src/features/metrics/`
- `frontend/src/lib/http/`
- `frontend/src/store/`
