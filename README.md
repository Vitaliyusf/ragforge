# RAGForge

Production-grade Retrieval-Augmented Generation platform with distributed microservices, event-driven messaging, and real-time document chat.

## Problem

Most RAG demos are a single script with a single endpoint. This project tackles the harder production-shaped concerns:

- **Real-time chat** over retrieved document context via WebSocket
- **Document ingestion** and embedding as independent, scalable services
- **Hybrid messaging**: RabbitMQ native RPC for gateway ↔ service calls; Kafka for the durable embedding event pipeline
- **Dedicated boundaries** for vector search, model serving, memory, and file management
- **Multi-tenant isolation** with tenant/user ownership enforced in MongoDB and Qdrant queries
- **Admin/user RBAC** with administrator-only files, logs, operational traces, and guardrail approval
- **Browser UI** that works against the full distributed stack

## Architecture

```
Browser (:3000)
  │
  ├─ HTTP ────────────► Gateway (:8000) ──────────────────────────────────┐
  │                                                                        │ MongoDB (:27017)
  │         RabbitMQ  ragapp.requests  direct exchange                     │
  │         ┌──────────────────────────────────────────────┐               │
  │         │  per-request exclusive reply queue per call  │               │
  │         └──────────────────────────────────────────────┘               │
  │                   │         │         │         │         │            │
  │              llm_agent   files     memory   vector_db  embedding  ─────┘
  │              (:8001)    (:8005)   (:8007)   (:8006)    (:8002)
  │                 │          │         │          │
  │              HTTP       MongoDB   MongoDB    Qdrant
  │                │        (:27017)  (:27017)  (:6333)
  │             vLLM                  Qdrant
  │            (:8008,               (:6333)
  │             GPU)
  │
  └─ Socket.IO ────► RAG (:8004) ─── MongoDB (:27017)  [conversation store]
                       │
                       │  RabbitMQ RPC per turn:
                       ├──► embedding  (encode query)
                       ├──► vector_db  (retrieve chunks)
                       ├──► llm_agent  (stream answer)
                       └──► memory     (load / persist context)

Embedding pipeline  (Kafka — durable, replayable event stream):

  files ──► embedding.jobs.requested ──► embedding
                                           ├──► vector_db.upsert.requested ──► vector_db
                                           └──► embedding.jobs.completed
```

| Transport | Pattern | Used for |
|-----------|---------|----------|
| **RabbitMQ** | Native RPC (exclusive reply queues) | All gateway ↔ service calls · RAG orchestration |
| **Kafka** | Durable event stream | Embedding pipeline: files → embedding → vector_db |
| **Socket.IO** | Streaming | Browser ↔ RAG real-time chat |
| **HTTP** | REST | Browser → Gateway management · llm_agent → vLLM |

### Why hybrid messaging?

The previous architecture ran all traffic over Kafka, including synchronous request/reply flows. That required a manual RPC layer: a shared `gateway.replies` topic, a `RequestResponseMatcher` (correlation-ID → `asyncio.Future` map), and a `GatewayKafkaReplyRouter` background thread — ~300 lines to simulate what RabbitMQ does natively.

RabbitMQ's exclusive auto-delete reply queues handle the RPC pattern directly. Kafka stays for the embedding pipeline, where durability and replay on failure actually matter.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | Next.js 14, React 18, Redux Toolkit, Tailwind CSS, Socket.IO, Framer Motion |
| Backend | Python 3.11, FastAPI, Pydantic, pydantic-settings |
| Messaging | RabbitMQ 3.13 (aio-pika, native RPC) · Apache Kafka (embedding pipeline) |
| Data | MongoDB 7, Qdrant (vector store) |
| AI/ML | vLLM (GPU inference), sentence-transformers (embeddings), cross-encoder reranking |
| Infra | Docker Compose, multi-stage builds, uv package manager |

## Results / Metrics

- 8 backend microservices + 1 Next.js frontend in a single `docker compose up`
- Hybrid RabbitMQ/Kafka messaging: native RPC for gateway flows, durable event stream for the embedding pipeline
- Real-time chat with hybrid search (vector + keyword), optional cross-encoder reranking
- LangChain tool-calling memory agent with consolidation/deduplication
- QLoRA fine-tuning pipeline (dataset upload, training, adapter registry) — hidden by default in public stack
- Centralized HTTP client with timeout, retry, and exponential backoff on both frontend and backend
- 40+ automated tests across unit, integration, and guardrail layers

These are repository and runtime metrics, not benchmark claims.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA drivers (for vLLM model serving)
- ~8 GB VRAM minimum (default model: Qwen2.5-7B-Instruct-GPTQ-Int4)

### Run

```bash
# 1. Clone and configure
git clone https://github.com/Vitaliyusf/ragforge.git && cd ragforge
cp .env.example .env

# 2. Replace every replace-* value. Generate independent secrets; do not reuse them.
#    Optionally set HF_TOKEN if the selected model is gated.

# 3. Start the full stack
docker compose --env-file .env up --build
```

First run takes 3-5 minutes for vLLM to download the model. Watch with:
```bash
docker compose logs -f vllm   # ready when "Application startup complete" appears
```

### Access

| Service | URL |
|---------|-----|
| UI | http://localhost:3000 |
| Gateway API docs | http://localhost:8000/docs |
| RAG Socket.IO | http://localhost:8004/socket.io |

MongoDB, RabbitMQ, Kafka, Qdrant, vLLM and all worker APIs are intentionally not bound to a host port. Access them with `docker compose exec` only when operationally necessary.

On first run the UI shows a one-time setup screen: the first account you register becomes the workspace administrator, and the setup endpoint closes permanently once any user exists. For non-interactive (scripted) deployments you can instead pre-seed the admin by setting `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`. See [the multi-tenancy and security runbook](docs/multi-tenancy-security-and-migration.md) for user management, additional tenant provisioning, legacy migration, production TLS, and release gates.

## Project Structure

```
backend/
  gateway/      HTTP API boundary — rate limiting, circuit breakers, RabbitMQ RPC client
  llm_agent/    Typed LLM orchestration — chat, summary, metadata, model management
  embedding/    Sentence-transformer embeddings + file extraction (PDF, DOCX, MD, TXT)
  rag/          Real-time chat orchestrator — hybrid search, reranking, evaluation, Socket.IO
  files/        File ingestion, review workflow, audit trail
  vector_db/    Qdrant vector storage and retrieval gating
  memory/       Chat persistence + long-term memory (LangChain tool-calling agent)
  shared/       Cross-cutting: metrics, retry, circuit breaker, prompt guard, rate limiter
docker/
  requirements-base.txt   Shared Python dependency layer
frontend/                 Next.js 14 app — chat, files, logs, models, config, health, memory
tests/                    Repo guardrails plus chat and ingestion smoke fixtures
docker-compose.yml        Full stack definition
docker-compose.prod.yml   HTTPS/same-origin production ingress overlay
.env.example              All configuration variables with safe defaults
docs/multi-tenancy-security-and-migration.md  RBAC, security and migration runbook
```

## Development

```bash
# Install dev tools (type checking, linting, testing)
pip install -r backend/requirements-dev.txt

# Type-check shared library and gateway (strict)
mypy backend/shared backend/gateway/app --config-file mypy.ini

# Lint
ruff check backend/

# Run unit tests
pytest backend/
```

### Compose smoke checks

With the stack running, the chat smoke check validates Socket.IO, RAG orchestration,
RabbitMQ RPC, token streaming, and persistence:

```bash
docker compose exec -T frontend node < tests/smoke_chat.js
```

The ingestion fixture exercises the Gateway upload endpoint and the durable Kafka
pipeline through extraction, embedding, and Qdrant indexing:

```bash
curl -F "file=@tests/fixtures/smoke_ingestion.txt;type=text/plain" \
  http://localhost:8000/v1/files/upload
```

## Security scope

The application uses opaque server-side sessions, CSRF and Origin validation, short-lived signed service tickets, tenant-scoped persistence, protected vector/model APIs, strict upload validation and fail-closed guardrail review. The production overlay terminates TLS and uses secure `__Host-` cookies.

Application controls alone are not a certification. Internet production still requires external secret/KMS management, encrypted disks and backups, MFA/enterprise identity for admins, rate limiting at ingress, vulnerability/image scanning, monitoring, a restore drill and an independent penetration test. The runbook tracks these explicitly.

## Public Repo Scope / Limitations

This repository is a curated, history-free snapshot of the main development repo:

- **Included**: chat, retrieval, file ingestion, model management, config, memory, and health flows
- **Excluded**: private git history, internal operations docs, CI/CD pipelines, internal tooling
- **Hidden by default**: Training tab (finetuning service not in default compose stack; set `NEXT_PUBLIC_ENABLE_TRAINING_TAB=true` to expose)
- **GPU required**: The default compose stack requires an NVIDIA GPU for vLLM. Without one, all services except vLLM will start, but chat/RAG flows will fail at inference time
- **Verified end-to-end**: This snapshot was exercised with the full GPU Compose stack, including document ingestion to Qdrant and streamed RAG chat through RabbitMQ
