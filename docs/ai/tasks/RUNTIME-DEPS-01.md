# RUNTIME-DEPS-01 — Runtime and dependency modernization

**Status:** completed / historical — runtime/toolchain migration task; it owns the versions it names. The current runtime is `docs/ai/RUNTIME_CONTRACT.md`.

**Phase:** Career-first foundation  
**Priority:** P0  
**Branch:** `chore/runtime-dependency-modernization`  
**Replaces:** planned `PY-01` + later broad `DEPS-01`  
**Depends on:** `TEST-01` COMPLETE / CI green

## Goal

Modernize the entire RagForge runtime and dependency surface in one controlled task:

- Python 3.11 → Python 3.12
- Node.js 20 (EOL) → Node.js 24 LTS
- upgrade high-value/security/runtime dependencies
- remove dependencies and legacy providers that are provably unused
- reduce duplicate version ownership across service requirements
- preserve application behavior
- do not blindly upgrade every package to latest
- leave high-risk, low-ROI major migrations explicitly deferred

The objective is **not** “all packages latest”.
The objective is:

```text
supported runtimes
+ fewer stale/security-sensitive dependencies
+ smaller dependency surface
+ less version drift
+ smaller/faster images where possible
+ clean CI
+ measurable before/after evidence
```

## Non-negotiable execution rules

- Work only on `RUNTIME-DEPS-01`.
- Preserve unrelated dirty files.
- Do not reset/stash/revert/clean.
- Do not commit or push.
- Do not run doctor.
- Do not repair or depend on a broken `.venv`.
- Use isolated `uv --python 3.12` for Python validation.
- Use the TEST-01 lanes/focused suites during implementation.
- Do not run the full repository suite after every dependency batch.
- Full backend/frontend validation runs once at final candidate state.
- Do not change the accepted vLLM runtime/model tuning.
- Do not upgrade stateful infrastructure majors (MongoDB/Kafka/RabbitMQ/Qdrant server) in this task.
- Do not introduce Kubernetes here.

---

# 1. Inventory everything first

Audit all version-owning files:

```text
.python-version
docker/requirements-base.txt
backend/requirements-test.txt
backend/requirements-dev.txt
backend/*/requirements.txt
frontend/package.json
frontend/package-lock.json
backend/*/Dockerfile
frontend/Dockerfile
.github/workflows/ci.yml
docker-compose.yml
docker-compose.prod.yml
.env.example / runtime docs where versions are documented
```

Produce a private machine-readable inventory under `.agent-private/` with:

```text
package
current version/range
latest stable
Python/Node requirement
direct import/caller count
services using it
candidate action: KEEP / UPGRADE / REMOVE / DEFER
reason
validation owner
```

Do not paste full package-manager output into the transcript.

Use current upstream release metadata, not memory.

---

# 2. Authoritative dependency ownership

Shared runtime dependencies should have one authoritative version owner where practical.

Prefer:

```text
docker/requirements-base.txt
    fastapi
    uvicorn
    aio-pika
    pymongo
    pydantic
    pydantic-settings
    prometheus-client
    prometheus-fastapi-instrumentator
```

Service `requirements.txt` files should contain only service-specific dependencies unless a service intentionally overrides a shared version.

Acceptance:
- no accidental duplicate pins for the same shared runtime package;
- any intentional override has a short reason;
- CI and Docker install the same dependency layers.

Do not create a dependency-management framework.

---

# 3. Runtime upgrades

## Python

Move canonical application runtime:

```text
3.11 → 3.12
```

Update:
- `.python-version`
- every Python service Dockerfile
- CI/setup references derived from `.python-version`
- docs/runtime comments that claim 3.11

Use a current Python 3.12 patch release, while keeping Docker images on the `python:3.12-slim` line unless exact digest pinning is already part of repository policy.

Do not change the vLLM image/runtime.

## Node.js

Current frontend base/CI is Node 20, which is EOL.

Move:

```text
Node 20 → Node 24 LTS
```

Update:
- frontend Dockerfile
- CI `NODE_VERSION`
- local/runtime documentation if present

Do not move to Node 26 Current; use LTS.

---

# 4. High-value upgrade candidates

The versions below are the audit starting point as of 2026-08-28.
Codex must re-check upstream metadata before editing.

## Backend core

| Package | Current | Candidate | Action |
|---|---:|---:|---|
| FastAPI | 0.115.12 | 0.141.1 | UPGRADE |
| Uvicorn | 0.34.0 | 0.52.4 | UPGRADE |
| Pydantic | 2.12.5 | 2.13.4 | UPGRADE |
| pydantic-settings | 2.7.1 | 2.15.0 | UPGRADE |
| PyMongo | 4.10.1 | 4.17.0 | UPGRADE |
| httpx | 0.28.1 | 0.28.1 stable | KEEP |
| python-multipart | 0.0.20 | 0.0.32 | UPGRADE |
| prometheus-client | 0.21.1 | 0.26.0 | UPGRADE |
| prometheus-fastapi-instrumentator | 7.1.0 | 8.1.0 | UPGRADE after metrics contract check |
| aio-pika | >=9.4,<10 | 9.6.2 within current major | UPGRADE; do not force 10.x |
| python-socketio | 5.10.0 | 5.16.4 | UPGRADE |
| aiohttp | 3.9.1 | 3.14.3 | UPGRADE |

### Why
These are active runtime/framework/transport dependencies and several are substantially stale. The upgrades improve current Python compatibility, maintenance/security posture, and in some cases performance/bug fixes.

---

# 5. Data/vector/document dependencies

| Package | Current | Candidate | Action |
|---|---:|---:|---|
| NumPy (RAG/Embedding) | 1.24.3 | 1.26.4 first | UPGRADE for Python 3.12 |
| NumPy (Vector) | 1.26.4 | align authoritative version | UNIFY |
| qdrant-client | 1.12.1 | 1.19.0 | UPGRADE |
| PyMuPDF | 1.24.14 | 1.28.2 | UPGRADE |
| python-docx | 1.1.2 | 1.2.0 | UPGRADE |
| docx2txt | 0.8 | 0.9 | UPGRADE if still canonical/reachable |
| kafka-python | 2.0.2 | 2.3.2 first | UPGRADE within 2.x; defer 3.x major |

### NumPy policy
Do **not** jump directly from 1.24.3 to NumPy 2.5.x merely because it is latest.

Use 1.26.4 as the first Python-3.12-compatible baseline because:
- it is the last 1.x release;
- it supports Python 3.12;
- Vector service already uses it;
- it minimizes unrelated numerical compatibility churn.

A NumPy 2.x migration can be tested later with embedding/vector benchmarks if there is a measured benefit.

---

# 6. Embedding / Hugging Face dependency audit

Current embedding stack includes:

```text
sentence-transformers==3.4.1
langchain-huggingface==0.1.2
huggingface_hub==0.28.1
```

Current releases are materially newer:
- sentence-transformers 6.x
- langchain-huggingface 1.2.x
- huggingface-hub 1.x

Do not blindly upgrade all three.

First determine canonical ownership:

1. Is direct `SentenceTransformerModel` the production embedding implementation?
2. Is `LangChainEmbeddingModel` actually selectable/used?
3. Are both intentionally supported?

### If LangChain embedding path is unused/noncanonical
Prefer:
- keep/upgrade direct `sentence-transformers`;
- remove `langchain-huggingface` and the dead implementation if safe and explicitly proven;
- remove direct `huggingface_hub` pin if no RagForge code owns that dependency.

### If both are supported
Upgrade the group together to a mutually compatible tested set.

### Embedding validation
For a fixed model and fixed fixture strings:
- embedding dimension unchanged;
- finite values;
- normalized vector invariant preserved;
- pairwise cosine ordering preserved;
- no unexpected model-name/default drift;
- batch/single equivalence within tolerance.

Do not claim retrieval quality improvement from a library upgrade unless Retrieval220 actually shows it.

---

# 7. LLM Agent heavy-stack audit

Current `llm_agent` contains:

```text
torch==2.0.0
transformers==4.35.0
accelerate==0.24.0
sentencepiece==0.1.99
tiktoken==0.5.0
```

These are highly stale and `torch==2.0.0` is not an acceptable basis for a Python 3.12 migration.

However, the canonical RagForge runtime is vLLM, and these heavy packages appear to exist for the Hugging Face fallback/provider.

## Required decision

Audit:
- config defaults
- frontend/config controls
- runtime factory callers
- docs
- CI
- tests
- real supported deployment paths

### If Hugging Face provider is not a real supported runtime
Prefer **REMOVE**, not upgrade:

```text
HuggingFaceClient
torch
transformers
accelerate
sentencepiece
tiktoken
```

but only remove packages with no remaining direct/transitive RagForge need.

This is a high-value optimization because it can reduce:
- image size
- CI dependency-install time
- CVE/attack surface
- dependency resolution complexity

Record exact before/after image size and CI install duration.

### If Hugging Face provider is genuinely supported
Do not silently remove it.

Choose a Python-3.12-compatible tested stack and validate the provider separately.
Do not jump all the way to Transformers 5.x/Torch 2.13 solely for freshness if that creates a large behavior migration.

If preserving the provider would make RUNTIME-DEPS-01 balloon into a separate ML runtime migration, report that fact and keep the smallest compatible supported set.

---

# 8. Memory / LangChain stack

Current:

```text
langchain==1.2.12
langchain-openai==1.1.11
langchain-core==1.2.18
```

Audit current mutually compatible releases.

Starting candidates:
```text
langchain ~1.3.x
langchain-openai ~1.6.x
langchain-core ~1.6.x
```

Upgrade as one coherent group only.

Validation:
- memory agent creation;
- tool registration;
- invocation result parsing;
- recursion/termination behavior;
- direct ChatOpenAI/vLLM compatibility;
- existing `memory-agent`, `memory-core`, and compatibility lanes.

Do not use this task to redesign the Memory Agent.

---

# 9. Defer high-risk / low-ROI Python majors

Explicitly audit but normally DEFER:

## LangGraph
Current:
```text
0.2.74
```
Current upstream is 1.x.

Do not perform a 0.2 → 1.x migration inside generic dependency modernization unless:
- current code requires it for Python 3.12/security;
- focused RAG/Files graph tests prove compatibility;
- migration is small.

The roadmap already plans to remove fake Files LangGraph ownership and later simplify RAG orchestration.

## LangSmith
Current:
```text
0.3.13
```
Upstream is much newer.

Because `OBS-TRACE-01` plans to converge tracing toward OpenTelemetry/OpenInference and optional exporters, do not spend large effort migrating old LangSmith-specific wrappers here.

Only upgrade if it is low-risk and required by another selected package.

---

# 10. Test/dev toolchain

Current:

```text
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-mock==3.14.0
mypy==1.10.1
ruff==0.4.9
black==24.4.2
```

Current ecosystem is materially newer.

## Upgrade in this task
Evaluate as one test-runner batch:

```text
pytest 9.1.x
pytest-asyncio 1.4.x
pytest-mock current stable
```

Do this only after production/runtime dependency batches are green.

Use TEST-01 lanes to isolate any async fixture/loop-scope migration.

## Normally defer
Do not force these upgrades unless they are near-zero churn:

```text
ruff 0.4.9 → 0.16.x
mypy 1.10.1 → 2.x
black 24.4.2 → 26.x
```

Reason:
- current repository is green under its pinned tooling;
- newer Ruff/Mypy can surface large pre-existing rule/type debt;
- mass formatting/type cleanup has little career ROI and can bury the real runtime migration.

If upgraded, do it in an isolated batch with **no mass autofix/reformat** unless explicitly required.

---

# 11. Frontend modernization

Current major runtime:

```text
Node 20
Next 14
React 18.2
ReactDOM 18.2
```

Required target:

```text
Node 24 LTS
Next 16.3.3 or newer patched Active LTS in the 16.x line
React 19.2
ReactDOM 19.2
```

This is high priority because:
- Node 20 is EOL;
- Next 14 is far behind the current supported line;
- Next's August 2026 security release explicitly requires patched 16.3.x / 15.5.x versions for critical vulnerabilities.

Use the official Next codemod/migration guidance where useful, but inspect every code change.

Expected migration checks:
- `next lint` is removed in Next 16; replace with explicit lint tooling or delete the dead script if lint is handled elsewhere;
- Node >=20.9 requirement is satisfied by Node 24 LTS;
- React 19 compatibility;
- Next 16 build uses Turbopack by default;
- App/Pages Router behavior remains unchanged;
- env/config handling unchanged.

Other direct frontend dependencies:
- upgrade safe patch/minor versions (`socket.io-client 4.8.3`, Redux Toolkit 2.12.x, Vite React plugin current, etc.);
- use `npm outdated` to classify all remaining direct packages;
- do not migrate Tailwind 3 → 4 or Framer Motion 12 → 13 merely for freshness unless the migration is trivial and tests/build remain clean.

No new frontend framework migration.

---

# 12. Infrastructure image audit — audit now, do not major-upgrade state

Audit current Compose images:

```text
mongo:7
zookeeper:3.9
confluentinc/cp-kafka:7.5.0
qdrant/qdrant:v1.18.2-unprivileged
vllm/vllm-openai:v0.27.1
rabbitmq:3.13-management
prom/prometheus:v2.55.1
caddy:2.11.4-alpine
```

Rules:
- vLLM: KEEP exactly accepted runtime.
- Mongo/Kafka/RabbitMQ: do not major-upgrade in this task.
- Qdrant server: keep unless a client compatibility/security issue requires a patch update.
- Prometheus major migration belongs with observability work.
- Caddy/ZooKeeper: patch/minor only if trivial and validated.
- Record deferred image upgrades in the final report.

---

# 13. Upgrade batching

One task, but execute in reversible logical batches.

## Batch A — runtime support
- Python 3.12
- Node 24 LTS
- Docker base images
- CI runtime versions
- NumPy 1.26.4 baseline

Run only runtime/import/config lanes.

## Batch B — core backend
- FastAPI
- Uvicorn
- Pydantic
- pydantic-settings
- PyMongo
- python-multipart
- aiohttp
- python-socketio
- Prometheus client/instrumentator
- aio-pika within 9.x

Run affected service/domain lanes.

## Batch C — data/vector/document
- qdrant-client
- PyMuPDF
- python-docx
- docx2txt if retained
- kafka-python within 2.x

Run vector/files/embedding lanes + targeted integration.

## Batch D — embedding / ML
- canonical embedding libraries only
- delete dead duplicate implementation/dependencies if proven safe
- resolve Hugging Face provider decision

Run embedding/LLM lanes and fixed-vector invariants.

## Batch E — Memory/LangChain
Upgrade only the coherent Memory group.

Run memory-core/memory-agent/memory-compat.

## Batch F — frontend
- Node 24
- Next 16 Active LTS patched
- React 19.2
- safe direct dependency updates

Run frontend feature lanes + production build.

## Batch G — test toolchain
Upgrade pytest/pytest-asyncio/pytest-mock as a coherent batch.

Run representative lanes first, then affected backend matrix.

Do not rerun already-passed broad gates after each batch unless a later batch can invalidate them.

---

# 14. Security and stale dependency evidence

Before and after:
- `pip-audit` or equivalent report-only audit across canonical Python dependency sets;
- `npm audit` report-only;
- `npm outdated`;
- Python outdated inventory from current package index metadata.

Do not fail the task on an advisory with no applicable fix.
Classify each finding:
- fixed;
- non-applicable;
- transitive;
- deferred with owner/task.

Do not hide advisories.

---

# 15. Performance / career evidence

Capture before/after:

```text
Python runtime
Node runtime
direct Python dependency count
direct frontend dependency count
outdated direct dependencies
known applicable vulnerabilities
per-service Docker image size
frontend image size
llm_agent image size
CI dependency-install duration
CI test/build duration
cold container start/readiness if cheap/repeatable
```

Especially report:
- heavy packages removed;
- image-size reduction;
- CI install-time reduction;
- number of duplicated pins removed.

These are useful CV/interview evidence only if measured.

Example allowed final evidence:
> Removed an unused local-HF inference stack from the canonical vLLM service path, reducing the LLM Agent image by X% and CI dependency setup by Y%.

Do not invent X/Y.

---

# 16. Validation

During implementation:
- exact TEST-01 lanes only.

Before finalizing:
1. all backend service lanes affected by upgraded packages;
2. full backend matrix once;
3. shared suite;
4. root/repo contract tests;
5. full frontend suite once;
6. Next production build;
7. Docker builds for every changed application image;
8. minimal Compose startup/readiness;
9. chat smoke;
10. ingestion→embedding→Qdrant smoke;
11. Memory Agent smoke;
12. Ruff with the repository's canonical version;
13. mypy only on currently authoritative typed scope;
14. `git diff --check`;
15. GitHub Actions is final clean-environment authority.

Do not run Smoke30/Retrieval220/Full240 unless an ML/embedding library change is shown to alter model/retrieval semantics.
If embedding outputs change materially, run Retrieval220 before accepting that specific upgrade.

---

# 17. Completion report

Report exact before/after table:

```text
runtime:
  Python:
  Node:
  Next:
  React:

dependencies:
  upgraded:
  removed:
  kept:
  deferred:

authoritative shared pins before/after:
duplicate pins removed:

security:
  Python applicable advisories before/after:
  npm applicable advisories before/after:

images:
  gateway before/after:
  rag before/after:
  files before/after:
  embedding before/after:
  vector_db before/after:
  llm_agent before/after:
  memory before/after:
  frontend before/after:

CI:
  dependency install before/after:
  backend test matrix before/after:
  frontend test/build before/after:

heavy ML stack:
  HuggingFace provider status:
  torch status:
  transformers status:
  accelerate status:
  sentencepiece status:
  tiktoken status:

deferred major migrations:
  LangGraph:
  LangSmith:
  NumPy 2.x:
  kafka-python 3.x:
  Ruff:
  mypy:
  Black:
  Tailwind 4:
  Framer Motion 13:
  stateful infrastructure images:
```

Also report:
- production files added/deleted;
- dependency files changed;
- lockfiles changed;
- compatibility paths removed;
- any behavior change required by Next/React/framework migration;
- unresolved blockers.

STOP at RUNTIME-DEPS-01 completion.
Do not start HEALTH-01.
