# Task Index

Read only the requested task file under `docs/ai/tasks/`.

## AGENT

- **AGENT-01** — Memory agent server-side mutation policy — `feat/memory-agent-policy`
- **AGENT-02** — Structured memory tool protocol and termination — `refactor/memory-agent-tool-protocol`
- **AGENT-03** — Memory agent evaluation harness — `feat/memory-agent-evals`
- **AGENT-04** — Tenant-scoped general agent mode — `feat/rag-agent-mode`

## APP

- **APP-01** — ApplicationRuntime and FastAPI dependency ownership — `refactor/service-runtime-containers`

## BENCH

- **BENCH-01** — Reproducible vLLM benchmark harness — `feat/vllm-benchmarks`
- **BENCH-02** — System load, ingestion and RPC benchmarks — `feat/system-benchmarks`

## BMARK

- **BMARK-01** — Benchmark dataset parser — `feat/benchmark-dataset-parser`
- **BMARK-02** — Golden set import UI — `feat/benchmark-dataset-import-ui`
- **BMARK-03** — Automatic filename label resolution — `feat/eval-file-label-resolution`
- **BMARK-04** — Deterministic chunk labels and readiness — `feat/eval-chunk-label-resolution`
- **BMARK-05** — Benchmark dataset reproducibility — `feat/eval-dataset-reproducibility`
- **BMARK-06** — Full diagnostic benchmark orchestrator — `feat/diagnostic-benchmark-runner`
- **BMARK-07** — Automatic benchmark manifest — `feat/benchmark-run-manifest`
- **BMARK-08** — Benchmark retrieval diagnostics — `feat/benchmark-retrieval-diagnostics`
- **BMARK-09** — Benchmark failure attribution — `feat/benchmark-failure-attribution`
- **BMARK-10** — Benchmark quality and latency summary — `feat/benchmark-result-summary`
- **BMARK-11** — Prometheus benchmark snapshots — `feat/benchmark-prometheus-snapshots`
- **BMARK-12** — Diagnostic ZIP export — `feat/benchmark-diagnostic-export`
- **BMARK-13** — Benchmark Center UI — `feat/benchmark-center-ui`
- **BMARK-14** — Benchmark run comparison — `feat/benchmark-run-comparison`
- **BMARK-15** — Benchmark Center hardening — `chore/benchmark-center-hardening`

## CHAOS

- **CHAOS-01** — Controlled chaos and recovery suite — `feat/chaos-recovery-tests`

## CI

- **CI-01** — CI build, security and RAG regression gates — `ci/harden-quality-gates`

## CLEAN

- **CLEAN-01** — Remove confirmed dead compatibility code — `chore/remove-dead-compat-code`

## DEPS

- **DEPS-01** — Staged dependency modernization — `chore/upgrade-python-web-stack`
- **DEPS-02** — Qdrant client upgrade — `chore/upgrade-qdrant-client`
- **DEPS-03** — Kafka client upgrade — `chore/upgrade-kafka-client`
- **DEPS-04** — Embedding library upgrade experiment — `chore/upgrade-embedding-stack`
- **DEPS-05** — LangGraph major-version migration — `chore/upgrade-langgraph`

## DIST

- **DIST-01** — Canonical turn persistence with outbox — `feat/conversation-outbox`
- **DIST-02** — Kafka delivery contracts and schema versioning — `feat/kafka-delivery-contracts`
- **DIST-03** — Distributed tenant-aware rate limiting — `fix/distributed-rate-limits`

## DOCKER

- **DOCKER-01** — Container image and dependency cleanup — `chore/container-image-cleanup`

## DOCS

- **DOCS-01** — Architecture credibility documentation — `docs/architecture-credibility`

## EMBED

- **EMBED-01** — Canonicalize embedding runtime and retire legacy paths — `refactor/embedding-runtime`

## EVAL

- **EVAL-01** — Eval candidate depth correctness — `fix/eval-candidate-depth`
- **EVAL-02** — Dataset version and canonical hash — `feat/eval-dataset-versioning`
- **EVAL-03** — Stale eval label validation — `feat/eval-stale-label-validation`
- **EVAL-04** — Effective eval configuration snapshot — `fix/eval-effective-config-snapshot`
- **EVAL-05** — Eval run leases and crash recovery — `feat/eval-run-leases`
- **EVAL-06** — Pipeline-mode evaluation — `feat/eval-pipeline-modes`
- **EVAL-07** — Deterministic failure attribution — `feat/eval-failure-attribution`

## FILES

- **FILES-01** — Fix Mongo transaction fallback semantics — `fix/files-transaction-fallback`

## FRONT

- **FRONT-01** — Batch chat streaming renders — `perf/chat-stream-rendering`
- **FRONT-02** — Files UI/data-flow scalability — `perf/files-data-flow`
- **FRONT-03** — Metrics frontend component consolidation — `refactor/metrics-components`

## METRICS

- **METRICS-01** — Metrics semantic corrections — `fix/metrics-semantics`

## OBS

- **OBS-01** — Separate eval and live operational metrics — `feat/metrics-traffic-class`
- **OBS-02** — Distributed observability, SLOs and GPU telemetry — `feat/distributed-observability`

## PERF

- **PERF-01** — Async RAG persistence and checkpoint retention — `perf/rag-async-persistence`

## QUAL

- **QUAL-01** — Expected claim coverage — `feat/eval-expected-claim-coverage`
- **QUAL-02** — Claim-citation edge evaluation — `feat/citation-edge-evaluation`
- **QUAL-03** — Deterministic claim support metrics — `feat/claim-quality-metrics`

## RAG

- **RAG-01** — Fix Pass2 global ranking — `fix/rag-pass2-global-ranking`
- **RAG-02** — Bounded parallel subquery retrieval — `perf/rag-parallel-subquery-retrieval`
- **RAG-03** — Token-aware diverse context assembler — `feat/rag-context-assembler`
- **RAG-04** — Real cross-encoder reranking — `feat/cross-encoder-reranking`
- **RAG-05** — True dense+sparse hybrid retrieval — `feat/hybrid-retrieval`

## REFACTOR

- **REFACTOR-01** — Decompose oversized orchestration modules — `refactor/graph-modules`

## RUNTIME

- **RUNTIME-01** — Runtime and container hardening — `chore/production-runtime-hardening`

## SAFE

- **SAFE-01** — Fail-closed streaming output safety — `fix/streaming-output-guardrail`

## SHARED

- **SHARED-01** — Consolidate shared service contracts — `refactor/shared-service-contracts`

## TRACE

- **TRACE-01** — Structured retrieval diagnostics — `feat/rag-retrieval-diagnostics`

## TYPES

- **TYPES-01** — Strengthen critical contracts and type checking — `refactor/typed-contracts`

## VECTOR

- **VECTOR-01** — Versioned incremental vector index lifecycle — `feat/vector-index-lifecycle`
- **VECTOR-02** — Qdrant operation optimizations — `perf/qdrant-operations`
