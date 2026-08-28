# RagForge Roadmap V5 — Career-First + Frontend/Product Track

## Goal

Turn RagForge into a production-oriented Applied AI / RAG portfolio project with measurable engineering evidence across:

- correctness and CI discipline
- supported runtimes and dependency hygiene
- container/runtime security
- production architecture
- document ingestion and representation
- retrieval quality
- developer-grade frontend UX
- evaluation and observability
- Kubernetes/distributed production
- agentic workflows

The frontend/product track is not a cosmetic redesign. It must improve product clarity, architecture, maintainability, performance, accessibility, and the ability to inspect and operate the RAG system.

---

# Execution order

```text
Correctness
    ↓
Modern runtime
    ↓
Production foundation
    ↓
Architecture simplification
    ↓
Frontend / Product foundation
    ↓
Document representation
    ↓
Retrieval quality
    ↓
Observability + performance
    ↓
Kubernetes / distributed production
    ↓
Agents
```

---

# Current / immediate

## RUNTIME-DEPS-01 — `chore/runtime-dependency-modernization`
Status: closeout / final CI authority

Purpose:
- Python 3.12
- Node 24 LTS
- dependency modernization
- shared pin consolidation
- security reduction
- Next 16 / React 19
- preserve retrieval semantics

Exit:
- final CI green
- no material retrieval-quality regression
- close task; do not keep tuning dependencies

---

## SEC-03 — `fix/non-root-containers`

Run application containers as non-root without breaking model cache, uploads, temp files, readiness, or service startup.

Required validation:
```text
changed image builds
→ runtime user/permissions checks
→ /live + /ready
→ chat smoke
→ ingestion/upload smoke
→ git diff --check
```

---

## DOCKER-BASE-01 — `chore/docker-runtime-baseline`

Converge dev/prod Docker runtime structure, improve image ownership/layers, slim frontend runtime, remove avoidable runtime dependencies, and establish a clean Compose baseline.

Evidence:
- per-image size before/after
- frontend runtime image size
- llm_agent runtime image size
- build duration
- cold readiness where repeatable

---

## RAG-RESUME-01 — `fix/rag-extended-resume-stages`

Make extended RAG stages resumable/recoverable with explicit state ownership and correct retry semantics.

---

## CONFIG-01 — `fix/runtime-config-control-plane`

Make runtime configuration ownership explicit and remove ambiguous/default-only control paths.

---

## SAFE-01 — `fix/streaming-output-guardrail`

Make streaming safety fail-closed and production-safe without corrupting normal answer delivery.

---

## FILES-01 — `fix/files-transaction-fallback`

Harden ingestion transaction/fallback semantics and failure recovery.

---

## MEM-CORRECT-01 — `fix/memory-error-semantics`

Correct memory error/result semantics so failures are not represented as successful business outcomes.

---

## SHARED-02 — `refactor/shared-contracts-v2`

Simplify shared service contracts and remove duplicated/ambiguous transport behavior.

---

# Architecture simplification

## EMBED-01
Simplify embedding ownership and keep one canonical production embedding path.

## FILES-02
Remove fake/duplicate orchestration ownership from Files and simplify ingestion execution boundaries.

## LLM-CTRL-01
Simplify model/runtime control paths around the canonical vLLM production path.

---

# Frontend / Product Track

The following tasks form one deliberate track. Refactor only the touched domain in each task; do not create a frontend mega-refactor.

```text
FRONT-FOUNDATION-01
↓
CHAT-01
↓
FILES-LIST-01
↓
EVAL-UX-01
↓
PRODUCT-01
↓
OBS-UX-01
↓
FRONT-POLISH-01
```

## FRONT-FOUNDATION-01 — `refactor/frontend-foundation`

Refactor frontend architecture and styling foundations before major redesign.

Core outcomes:
- clear feature boundaries
- reusable primitives
- design tokens
- canonical status vocabulary
- shared loading/error/empty patterns
- CSS strategy cleanup
- dead-code removal in touched scope
- no unnecessary styling framework
- Tailwind 4 decision made once, before redesign
- performance baseline captured

---

## CHAT-01 — `feat/chat-product-experience`

Turn Chat into a clean knowledge-user experience with an optional engineering inspector.

Core outcomes:
- clean answer + sources + feedback
- compact quality summary
- raw prompt/model/UUID/timestamps removed from default UI
- Developer Inspector drawer
- retrieval/context/generation/quality/trace details
- correct RTL/LTR behavior
- conversation persistence/title behavior
- real stage-aware execution status only when backed by real state
- long-chat performance validation

---

## FILES-LIST-01 — `feat/knowledge-operations-table`

Replace the document-card gallery with a scalable document operations table.

Core outcomes:
- compact row-based document list
- search/sort/filter
- processing/failure expansion
- visible ingestion pipeline
- document drawer
- bulk operations
- virtualization/pagination when justified
- 1,000-row responsiveness validation
- failure state is actionable: what / why / next action

---

## EVAL-UX-01 — `refactor/eval-run-report`

Turn Eval from a long card wall into an inspectable run report.

Core outcomes:
- run header
- execution flow
- KPI summary
- tabs: Overview / Retrieval / Quality / Failures / Items / Configuration
- human-readable failures
- technical details collapsed
- trace/log deep links where available
- comparison integrity when configs differ
- run labels instead of raw UUIDs

---

## PRODUCT-01 — `feat/product-navigation-and-status-model`

Create a coherent product information architecture and role-aware navigation.

Product pillars:
```text
Workspace
  Chat
  Knowledge

Quality
  Eval
  Metrics

Operations
  Models
  Logs
  Health

Administration
  Users
  Settings
```

Also:
- canonical terminology
- role-aware visibility
- canonical status taxonomy
- replace vague duplicated `Live` with one Global Activity indicator
- remove implementation concepts from default user navigation

---

## OBS-UX-01 — `feat/observability-product-workflows`

Connect Chat, Knowledge, Eval, Metrics, Logs, and Health into one inspectable operational workflow.

Core outcomes:
- Chat → trace
- Eval failure → trace
- File failure → ingestion trace
- Metrics anomaly → affected traces
- Health issue → filtered logs
- metrics carry explicit scope/sample/source/freshness semantics
- tenant/global/model scope is never implicit

Do this only when backend trace/data contracts are ready enough to support real links. Never fake progress or trace data.

---

## FRONT-POLISH-01 — `refactor/frontend-production-polish`

Final production-quality pass after workflows and information architecture are stable.

Core outcomes:
- accessibility
- keyboard navigation
- responsive laptop layouts
- reduced motion
- loading/partial/stale/delayed/unknown states
- destructive action UX
- notification/toast consistency
- surface/density/typography cleanup
- demo-ready seeded workspace
- final CSS/bundle/image evidence

---

# Remaining foundation closeout

## TYPES-01
Reduce remaining type ambiguity and improve stable typed boundaries.

## SUPPLY-01
Supply-chain / dependency integrity / artifact hygiene.

## VALIDATE-01
Consolidate Baseline V1 evidence:
```text
before
after
methodology
result
limitations
resume/interview evidence
```

---

# Document Representation V2

```text
VECTOR-01
→ DOCPIPE-01
→ DOCPIPE-02
→ CHUNK-01
→ CHUNK-02
→ CHUNK-03
```

Goals:
- explicit vector/index contracts
- structured document representation
- deterministic extraction
- chunking strategies with measured tradeoffs

---

# Retrieval V2

```text
RAG-05   hybrid retrieval
→ RAG-04 cross-encoder reranking
→ RAG-06 context expansion / MMR / neighbors
→ VECTOR-02 Qdrant operational hardening
→ TRACE-01 retrieval diagnostics
```

---

# Quality / Observability

```text
QUAL-01
→ OBS-TRACE-01
→ EVAL-EXT-01
→ E2E-01
→ OBS-02
```

The frontend `OBS-UX-01` should consume these capabilities as they become available rather than inventing parallel instrumentation.

---

# Kubernetes

```text
K8S-01 stateless application platform
→ K8S-02 vLLM serving
→ K8S-03 optional stateful infrastructure
```

Do not introduce Kubernetes before Docker/runtime behavior is stable and measurable.

---

# Memory

```text
MEM-01
→ MEM-QUERY-01
→ MEM-02
→ MEM-03
```

---

# Agents

```text
AGENT-01 policy
→ AGENT-02 typed tools
→ AGENT-03 evals
→ AGENT-04 optional RAG agent
```

---

# Distributed production

```text
DIST-01 outbox
→ DIST-02 Kafka contracts
→ DIST-03 conditional rate limiting
→ CHAOS-01
→ DEPLOY-01
→ VALIDATE-02
```

---

# Frontend implementation policy

Every frontend task must follow:

```text
refactor touched scope
→ smallest focused tests
→ implement behavior
→ feature tests
→ production build
→ performance/UX evidence when relevant
→ diff audit
```

Rules:
- no broad unrelated cleanup
- remove dead code only in the touched domain
- split oversized components when boundaries are clear
- move API/data logic out of presentation components
- avoid duplicated derived state
- avoid unnecessary `useEffect`
- preserve Server/Client Component boundaries
- do not make components client-side without a concrete reason
- do not add a dependency unless it removes more complexity than it introduces
- no fake loading/progress stages
- status must never rely on color alone
- respect reduced-motion
- large-list workflows must be measured, not assumed

---

# Styling strategy

Preferred stack:

```text
Tailwind
+ CSS variables / design tokens
+ class-variance-authority
+ clsx
+ tailwind-merge
+ CSS Modules only for genuinely complex local styling
+ Motion/Framer Motion only for state/layout animation
```

Do not add:
- MUI
- Chakra
- Emotion
- styled-components
- another utility-CSS framework
- Sass solely for organization

Tailwind 4:
- audit once in FRONT-FOUNDATION-01
- migrate before redesign only if browser support and migration cost are acceptable
- otherwise keep Tailwind 3
- do not migrate halfway through the redesign track

---

# Frontend evidence

Capture where relevant:

```text
production JS bundle
CSS output size
frontend Docker image size
build duration
frontend dependency count
custom CSS LOC
dead components/hooks/styles removed
duplicate style/token reduction
1,000-document list responsiveness
200-message chat responsiveness
accessibility findings
```

Do not invent metrics.

---

# Career narrative target

A future CV/interview statement should be backed by measured evidence and may eventually resemble:

> Designed and refactored a production-oriented RAG platform with scalable document operations, role-aware product navigation, inspectable AI answer traces, evaluation workflows, trustworthy observability, and a reusable frontend design system; reduced duplicated styling/runtime surface while preserving retrieval quality and improving operational debuggability.

Only use measured numbers when they exist.
