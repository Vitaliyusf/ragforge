# Common Call Paths

Navigation hints only; verify current source.

## Chat / RAG turn
```text
Frontend chat
  → Gateway chat/RAG façade
    → RAG
      → ConversationGraph
        → ConversationBackendClient
          → Memory
          → Embedding
          → Vector DB / Qdrant
          → LLM Agent / vLLM
      → persistence / metrics facts / trace
  → stream/final response
```

First paths:
- `frontend/src/features/chat/`
- `backend/gateway/app/services/`
- `backend/rag/app/services/conversation_graph.py`
- `backend/rag/app/services/conversation_backend_client.py`

## Golden-set evaluation
```text
Metrics/Eval UI
  → metrics service
  → Gateway metrics/eval API
  → RAG EvalStore / EvalRunner
      → base retrieval OR RAG graph
  → retrieval/quality metrics
  → run persistence
```

## File upload / ingestion
```text
Files UI / useFiles
  → fileService
  → Gateway Files façade
  → Files service/repository
  → ingestion workflow
      → extraction/chunking
      → Kafka embedding job
      → Embedding
      → Vector DB
      → Qdrant
  → stage/status updates
```

## Admin metrics
```text
Metrics UI
  → metricsService.js
  → Gateway MetricsService
      → RAG tenant-scoped facts
      → Files state/metrics
      → Prometheus operational metrics
      → Vector metrics where implemented
```

## Memory curation
```text
Conversation/chat-exit
  → Memory service
  → Memory Agent
      → list/add/update/delete/done tools
  → Memory repository
```

## Before adding a new call
Ask:
1. Which service owns the truth?
2. Does an existing client/action/route already expose it?
3. Can the current contract be extended instead of bypassed?
