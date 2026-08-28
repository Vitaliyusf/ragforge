# RAGForge — Master Roadmap V3

**Audit source snapshot:** `main @ 02ef9e161595a9f2d26fedabee35c81d07ffb2ca`  
**Active task files:** 54  
**Design rule:** fold small, behavior-neutral refactoring into the task that already touches the same concern. Standalone refactor work remains only for genuinely cross-cutting residual ownership/lifecycle problems.

## Completed before V3
- `CI-03` — COMPLETE
- `GEN-08` — COMPLETE
- `PROV-01` — COMPLETE
- `CLEAN-03` — COMPLETE
- `SEC-02` — COMPLETE
- `CI-04` — COMPLETE
- `CLEAN-01` — COMPLETE
- `DOC-01` — COMPLETE
- `RAG-01` — COMPLETE
- `PERF-01` — COMPLETE
- `RAG-02` — COMPLETE

## Execution order

### 0 Governance

1. **BRAIN-01 — Anti-monolith task and engineering guardrails** — P0 — `chore/ai-complexity-ratchet` — deps: —

### 1 Current hardening

2. **RAG-RESUME-01 — Make extended RAG checkpoint recovery unambiguous** — P0 — `fix/rag-extended-resume-stages` — deps: BRAIN-01
3. **CONFIG-01 — Make runtime configuration honest and deployment-owned** — P0 — `fix/runtime-config-control-plane` — deps: BRAIN-01
4. **RAG-03 — Token-aware diverse context assembler** — P0 — `feat/rag-context-assembler` — deps: RAG-RESUME-01, CONFIG-01
5. **SAFE-01 — Fail-closed streaming output safety** — P0 — `fix/streaming-output-guardrail` — deps: RAG-03
6. **FILES-01 — Fix Mongo transaction fallback semantics** — P0 — `fix/files-transaction-fallback` — deps: BRAIN-01
7. **MEM-CORRECT-01 — Fix Memory error semantics and failure classification** — P0 — `fix/memory-error-semantics` — deps: BRAIN-01
8. **HEALTH-01 — Standardize liveness and readiness contracts** — P1 — `fix/service-health-readiness` — deps: BRAIN-01
9. **SEC-03 — Run application containers as non-root** — P1 — `fix/non-root-containers` — deps: HEALTH-01
10. **TEST-01 — Restructure tests by contract and add highest-risk boundary coverage** — P1 — `test/contract-oriented-suites` — deps: RAG-03, SAFE-01, FILES-01, MEM-CORRECT-01
11. **SHARED-02 — Consolidate proven cross-cutting contracts without a shared god module** — P1 — `refactor/shared-contracts-v2` — deps: TEST-01
12. **DEPS-01 — Staged dependency and image-surface modernization** — P1 — `chore/staged-dependency-modernization` — deps: SHARED-02, SEC-03
13. **VALIDATE-01 — Baseline hardening release gate** — P0 — `release/baseline-validation-v1` — deps: DEPS-01

### 2 Simplification

14. **EMBED-01 — Canonicalize embedding runtime and retire legacy paths** — P1 — `refactor/embedding-runtime` — deps: VALIDATE-01
15. **FILES-02 — Simplify Files ingestion into an explicit state machine** — P1 — `refactor/files-ingestion-state-machine` — deps: VALIDATE-01, FILES-01
16. **LLM-CTRL-01 — Unify LLM control plane and simplify execution/provider ownership** — P1 — `refactor/llm-control-plane` — deps: CONFIG-01, VALIDATE-01
17. **CHAT-01 — Make completed-turn persistence server-owned** — P1 — `feat/server-owned-chat-persistence` — deps: VALIDATE-01
18. **FRONT-01 — Batch chat streaming renders and shrink ChatContext responsibility** — P1 — `perf/chat-stream-rendering` — deps: CHAT-01
19. **FILES-LIST-01 — Add scalable server-side file listing** — P1 — `perf/files-list-pagination` — deps: FILES-02
20. **PRODUCT-01 — Remove or graduate incomplete operator surfaces** — P2 — `chore/product-surface-hardening` — deps: CONFIG-01, VALIDATE-01
21. **APP-01 — Residual ApplicationRuntime and lifecycle consolidation** — P2 — `refactor/service-runtime-containers` — deps: EMBED-01, FILES-02, LLM-CTRL-01, CHAT-01
22. **TYPES-01 — Strengthen critical contracts incrementally** — P2 — `refactor/typed-contracts` — deps: APP-01

### 3 Document Representation V2

23. **VECTOR-01 — Versioned vector index lifecycle** — P0 — `feat/vector-index-lifecycle` — deps: VALIDATE-01
24. **DOCPIPE-01 — Introduce a canonical structured document model** — P0 — `feat/structured-document-contract` — deps: VALIDATE-01, FILES-02, EMBED-01
25. **DOCPIPE-02 — Add structured parser adapters and fallback policy** — P1 — `feat/document-parser-adapters` — deps: DOCPIPE-01
26. **CHUNK-01 — Structure-aware token-budgeted chunking baseline** — P0 — `feat/structured-token-chunking` — deps: DOCPIPE-01, VECTOR-01
27. **CHUNK-02 — Contextual chunk augmentation** — P1 — `feat/contextual-chunk-metadata` — deps: CHUNK-01
28. **CHUNK-03 — Benchmark advanced chunking strategies** — P2 — `exp/advanced-chunking` — deps: CHUNK-01, CHUNK-02
29. **CHUNK-04 — Agent-assisted document repair for low-confidence cases** — P3 — `feat/agentic-document-repair` — deps: DOCPIPE-02, CHUNK-03

### 4 Retrieval V2

30. **RAG-05 — True dense+sparse hybrid retrieval** — P1 — `feat/hybrid-retrieval` — deps: CHUNK-01, VECTOR-01
31. **RAG-04 — Add a real learned reranker** — P1 — `feat/cross-encoder-reranking` — deps: RAG-05
32. **RAG-06 — Neighbor expansion and evidence diversity policy** — P2 — `feat/retrieval-context-expansion` — deps: RAG-04, CHUNK-01, RAG-03
33. **VECTOR-02 — Optimize Qdrant operations after Retrieval V2 stabilizes** — P2 — `perf/qdrant-operations` — deps: RAG-06
34. **TRACE-01 — Deep structured retrieval diagnostics** — P2 — `feat/rag-retrieval-diagnostics-v2` — deps: RAG-05, RAG-04, RAG-06

### 5 Memory V2

35. **MEM-01 — Use real neural embeddings for long-term memory** — P1 — `feat/neural-memory-embeddings` — deps: LLM-CTRL-01, VECTOR-01
36. **MEM-QUERY-01 — Move Memory filtering/scoring data access out of Python scans** — P1 — `perf/memory-query-scaling` — deps: MEM-01
37. **MEM-02 — Repairable memory secondary-index reconciliation** — P1 — `feat/memory-index-reconciliation` — deps: MEM-01
38. **MEM-03 — Create a memory quality golden set** — P1 — `feat/memory-quality-evals` — deps: MEM-01, MEM-02
39. **AGENT-01 — Harden Memory agent server-side mutation policy** — P1 — `feat/memory-agent-policy` — deps: MEM-03, LLM-CTRL-01
40. **AGENT-02 — Typed Memory agent tool protocol and deterministic termination** — P2 — `refactor/memory-agent-tool-protocol` — deps: AGENT-01
41. **AGENT-03 — Memory agent evaluation harness** — P2 — `feat/memory-agent-evals` — deps: AGENT-02, MEM-03
42. **AGENT-04 — Tenant-scoped general agent mode** — P3 — `feat/rag-agent-mode` — deps: AGENT-03, RAG-06

### 6 Quality & Observability

43. **QUAL-01 — Consolidate claim coverage, citation edges and deterministic support metrics** — P2 — `feat/claim-quality-metrics-v2` — deps: VALIDATE-01
44. **OBS-TRACE-01 — Unify AI tracing on a vendor-neutral instrumentation layer** — P2 — `feat/otel-ai-tracing` — deps: LLM-CTRL-01, TRACE-01
45. **EVAL-EXT-01 — External eval calibration and Eval subsystem decomposition** — P2 — `feat/eval-calibration` — deps: QUAL-01, OBS-TRACE-01
46. **E2E-01 — Browser end-to-end critical-flow suite** — P1 — `test/browser-e2e` — deps: TEST-01, VALIDATE-01
47. **OBS-02 — SLOs, distributed observability and GPU/queue telemetry** — P2 — `feat/distributed-observability` — deps: HEALTH-01, OBS-TRACE-01

### 7 Distributed production

48. **DIST-01 — Canonical turn persistence with transactional outbox** — P2 — `feat/conversation-outbox` — deps: CHAT-01
49. **DIST-02 — Version Kafka delivery contracts and strengthen idempotency** — P2 — `feat/kafka-delivery-contracts` — deps: DIST-01, TEST-01
50. **DIST-03 — Distributed tenant-aware rate limiting when Gateway scales out** — P3 — `feat/distributed-rate-limits` — deps: DEPLOY-01
51. **CHAOS-01 — Controlled failure and recovery suite** — P2 — `test/chaos-recovery` — deps: DIST-01, DIST-02, HEALTH-01
52. **SUPPLY-01 — Supply-chain and artifact security gate** — P2 — `ci/supply-chain-hardening` — deps: DEPS-01, SEC-03
53. **DEPLOY-01 — Production deployment profile and stateful-service policy** — P2 — `chore/production-deployment-profile` — deps: SUPPLY-01, HEALTH-01

### 8 Final release

54. **VALIDATE-02 — Advanced platform release gate** — P0 — `release/advanced-validation-v2` — deps: DEPLOY-01, CHAOS-01, OBS-02

## Old task absorption / retirement map

- `REFACTOR-02` → LLM-CTRL-01
- `REFACTOR-03` → RAG-RESUME-01 + RAG-03 + SAFE-01
- `REFACTOR-04` → FILES-02 + DOCPIPE-01 + EMBED-01
- `REFACTOR-05` → MEM-CORRECT-01 + MEM-01 + MEM-QUERY-01 + MEM-02
- `REFACTOR-06` → EVAL-EXT-01
- `FRONT-02` → FILES-LIST-01
- `FRONT-03` → OBS-02
- `QUAL-02` → QUAL-01
- `QUAL-03` → QUAL-01
- `RUNTIME-01` → HEALTH-01 + SEC-03 + APP-01 + DEPLOY-01
- `DOCKER-01` → SEC-03 + DEPS-01 + SUPPLY-01
- `SHARED-01` → SHARED-02
- `DOCS-01` → superseded by completed DOC-01
- `CI-01 / CI-02` → superseded by completed CI-03 / CI-04
- `DEPS-02..05` → fold into staged DEPS-01 or a future isolated experiment only when required
- `OBS-01` → live/eval traffic separation already exists; remaining observability work is OBS-02
- `REFACTOR-01` → replaced by local-refactor budgets across domain tasks

## Why the old dedicated REFACTOR wave is removed

The previous plan deferred large-file cleanup into separate `REFACTOR-*` tasks. V3 changes the operating model:

- `conversation_graph.py` is reduced while implementing `RAG-RESUME-01`, `RAG-03`, and `SAFE-01`.
- `LLMService.execute` is reduced inside `LLM-CTRL-01`.
- Files orchestration is reduced inside `FILES-02`, `DOCPIPE-01`, and `EMBED-01`.
- Memory orchestration is reduced inside `MEM-CORRECT-01`, `MEM-01`, `MEM-QUERY-01`, and `MEM-02`.
- Eval runner/store are reduced inside `EVAL-EXT-01`.
- Frontend hotspots are reduced inside `FRONT-01`, `FILES-LIST-01`, and `OBS-02`.
- `APP-01` remains only as a residual cross-service runtime/lifecycle cleanup after domain tasks.

This avoids the pattern: feature → bigger monolith → separate refactor sprint → repeat.

## Release checkpoints

### Baseline V1 — `VALIDATE-01`
After the current correctness/security/simplification hardening, before changing document/index/retrieval semantics.

### Baseline V2 — `VALIDATE-02`
After structured documents, Retrieval V2, Memory V2, observability and production hardening.

## Benchmark discipline

- Correctness/internal refactor: focused tests + affected service suite.
- Document/index/retrieval semantics: Retrieval benchmark.
- Generation/safety semantics: targeted end-to-end/Smoke30.
- `Full240`: release gates, not every task.
- Change one major RAG variable per benchmark candidate.
- A rejected experiment should not remain as permanent production code/config.

## Default Codex invocation

```text
Execute docs/ai/tasks/<TASK-ID>.md exactly as written.

Read the task, current implementation, direct callers/tests, and only relevant repo-brain entries.
Use the task's Local refactor budget for the exact concern being changed.
Do not create a parallel legacy/v2 path unless the task explicitly requires temporary compatibility.
Do not run doctor as a generic prerequisite.
Do not repair .venv.
Do not commit or push.
```
