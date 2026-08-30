# RAGForge

[![CI](https://github.com/Vitaliyusf/ragforge/actions/workflows/ci.yml/badge.svg)](https://github.com/Vitaliyusf/ragforge/actions/workflows/ci.yml)

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
| Frontend | Next.js 16, React 19, Redux Toolkit, Tailwind CSS, Socket.IO, Framer Motion |
| Backend | Python 3.12, FastAPI, Pydantic, pydantic-settings |
| Messaging | RabbitMQ 3.13 (aio-pika, native RPC) · Apache Kafka (embedding pipeline) |
| Data | MongoDB 7, Qdrant (vector store) |
| AI/ML | vLLM (GPU inference), sentence-transformers (embeddings), dense-vector retrieval |
| Infra | Docker Compose, multi-stage builds, uv package manager |

## Results / Metrics

- 8 backend microservices + 1 Next.js frontend in a single `docker compose up`
- Hybrid RabbitMQ/Kafka messaging: native RPC for gateway flows, durable event stream for the embedding pipeline
- Real-time chat with hybrid retrieval and a pinned multilingual cross-encoder reranker
- LangChain tool-calling memory agent with consolidation/deduplication
- QLoRA fine-tuning pipeline (dataset upload, training, adapter registry) — hidden by default in public stack
- Centralized HTTP client with timeout, retry, and exponential backoff on both frontend and backend
- 1,200+ statically declared automated test cases across backend, frontend, and repository guardrail suites

These are repository and runtime metrics, not benchmark claims.

The default Compose profile fuses dense and sparse candidates with RRF, then
reranks a bounded pool of 20 passages with the pinned multilingual
`BAAI/bge-reranker-v2-m3` cross-encoder. A timeout or model error preserves the
retrieval ordering deterministically and is exposed in metrics and eval traces.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA drivers (for vLLM model serving)
- ~6 GB VRAM minimum (default model: RedHatAI/Qwen3.5-4B-quantized.w4a16)

The accepted default vLLM runtime profile is:

| Setting | Effective default |
|---------|-------------------|
| Image | `vllm/vllm-openai:v0.27.1` |
| Model | `RedHatAI/Qwen3.5-4B-quantized.w4a16` |
| Quantization | `compressed-tensors` |
| Model runner | V1 (`VLLM_USE_V2_MODEL_RUNNER=0`) |
| Context window | 10,240 tokens |
| GPU memory utilization | 0.85 |
| Maximum concurrent sequences | 4 |
| Maximum batched tokens | 2,048 |
| Performance mode | `interactivity` |
| Prefix caching | enabled |

These values are defaults, not requirements: operators can override the
corresponding variables in `.env`. The V1 runner is intentional for the
accepted WSL2/Docker Desktop deployment because the V2 runner requires CUDA UVA.
Per-action output-token defaults are documented in
[LLM output-token budgets](docs/operations/llm-output-token-budgets.md).

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

On Windows, steps 1-2 can be done for you — the script creates `.env` from the
template with an independent cryptographically random value per secret, and
leaves an existing `.env` untouched:

```powershell
pwsh ./scripts/initialize_docker_env.ps1
```

The first run must download the model and initialize vLLM, which can take several
minutes. Watch readiness with:
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

On first run the UI shows a one-time setup screen: the first account you register becomes the workspace administrator, and the setup endpoint closes permanently once any user exists. For non-interactive (scripted) deployments you can instead pre-seed the admin by setting `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`. See [the multi-tenancy and security runbook](docs/multi-tenancy-security.md) for user management, additional tenant provisioning, production TLS, and release gates.

## Project Structure

```
backend/
  gateway/      HTTP API boundary — rate limiting, circuit breakers, RabbitMQ RPC client
  llm_agent/    Typed LLM orchestration — chat, summary, metadata, model management
  embedding/    Sentence-transformer embeddings + file extraction (PDF, DOCX, MD, TXT)
  rag/          Real-time chat orchestrator — dense retrieval, score merge, evaluation, Socket.IO
  files/        File ingestion, review workflow, audit trail
  vector_db/    Qdrant vector storage and retrieval gating
  memory/       Chat persistence + long-term memory (LangChain tool-calling agent)
  logs/         Centralized structured log collection
  shared/       Cross-cutting: metrics, retry, circuit breaker, prompt guard, rate limiter
docker/
  requirements-base.txt   Shared Python dependency layer
frontend/                 Next.js 16 app — chat, files, logs, models, config, health, memory
scripts/                  Operator tooling (see Development)
deploy/Caddyfile          TLS terminating reverse proxy for the production overlay
tests/                    Repo guardrails plus chat and ingestion smoke fixtures
.github/workflows/ci.yml  Lint, type-check, and test matrix
docker-compose.yml        Full stack definition
docker-compose.prod.yml   HTTPS/same-origin production ingress overlay
.env.example              All configuration variables with safe defaults
docs/multi-tenancy-security.md  RBAC, tenant isolation, and security runbook
```

## Development

```bash
# Install dev tools (type checking, linting, testing).
# requirements-dev.txt includes backend/requirements-test.txt, the single
# canonical pytest/pytest-asyncio/pytest-mock set for the whole repository.
pip install -r backend/requirements-dev.txt

# Type-check shared library and gateway (strict)
mypy backend/shared backend/gateway/app --config-file mypy.ini

# Lint
ruff check backend/
```

Backend tests run per service. Each service imports its own code as `app.*` and
the vendored library as `shared.*` — the layout its image gets by copying both
into `/app` — so outside a container those two roots go on the path explicitly:

```bash
# One service
(cd backend/gateway && PYTHONPATH="$PWD:$PWD/.." pytest app/tests -q)

# All of them
for svc in embedding files gateway llm_agent memory rag vector_db; do
  (cd "backend/$svc" && PYTHONPATH="$PWD:$PWD/.." pytest app/tests -q) || break
done

# Shared library — from backend/, not backend/shared/, whose logging.py
# would otherwise shadow the standard library module of the same name.
(cd backend && PYTHONPATH="$PWD" pytest shared/tests -q)

# Frontend
(cd frontend && npm ci && npm test)

# Repo hygiene: secrets, stray caches, compose drift
pytest tests/test_public_repo_guardrails.py -q
```

Each service needs its own `requirements.txt` installed for its tests to
import; [the CI workflow](.github/workflows/ci.yml) does this per service and is
the authoritative reference for a working setup. Install into one Python 3.12
environment in this order, and never add a second pytest on top:

```bash
pip install -r docker/requirements-base.txt
pip install -r backend/<service>/requirements.txt   # repeat per service
pip install -r backend/requirements-test.txt        # last: owns the test runner
```

Service `requirements.txt` files carry runtime dependencies only. Test-runner
pins live solely in `backend/requirements-test.txt`, so installing several
services side by side can no longer downgrade pytest and break plugin loading.

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

This repository is a curated public snapshot of the main development repo. It
does not include the private development history, but it does include the public
CI workflow and the operator tooling needed to build, test, and run the snapshot:

- **Included**: chat, retrieval, file ingestion, model management, config, memory, and health flows
- **Project support included**: `.github/workflows/ci.yml`, public operator/security docs, initialization scripts, and repository guardrails
- **Excluded**: private development history and private internal operations artifacts
- **Hidden by default**: Training tab (finetuning service not in default compose stack; set `NEXT_PUBLIC_ENABLE_TRAINING_TAB=true` to expose)
- **GPU required**: The default compose stack requires an NVIDIA GPU for vLLM. Without one, all services except vLLM will start, but chat/RAG flows will fail at inference time
- **CI scope**: GitHub Actions runs Ruff, strict mypy, per-service backend tests, shared tests, frontend tests and production build, and public-repository guardrails; Python and frontend dependency audits are currently report-only
- **GPU validation is separate**: CI does not start the GPU Compose stack. The documented chat and ingestion smoke commands are the operator checks for live end-to-end behavior
