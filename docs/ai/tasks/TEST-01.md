# TEST-01 — Repository-wide test architecture and optimization

**Status:** completed / historical — retained as execution evidence. Runtime/tooling text here is superseded by `docs/ai/RUNTIME_CONTRACT.md`.

**Phase:** 1 — Current hardening  
**Priority:** P1  
**Branch:** `test/repo-test-architecture`

## Goal

Optimize the **entire RagForge test system**, not only RAG.

The goal is:

```text
smaller focused test files
+ clearer ownership
+ fewer duplicated assertions
+ explicit compatibility lanes
+ fast task-specific selection
+ less agent token usage
+ full confidence retained in CI/release
```

Do not optimize for a vanity test-count number.

## Repository-wide scope

Audit and optimize:

```text
backend/shared/tests
backend/gateway/app/tests
backend/rag/app/tests
backend/files/app/tests
backend/embedding/app/tests
backend/vector_db/app/tests
backend/llm_agent/app/tests
backend/memory/app/tests
frontend/src/**/*.test.*
tests/*
scripts/ai/check.py
docs/ai/TESTING.md
docs/ai/TESTING_OPTIMIZED.md
```

## Known hotspots from the repository audit

### RAG
- `test_eval_runner.py`
- `test_rag.py`
- `test_benchmark_runner.py`
- `test_eval_store.py`
- `test_benchmark_manifest.py`

### LLM Agent
- `test_llm_service.py`
- `test_provider_finish_reason.py`
- `test_answer_citations.py`
- `test_vllm_streaming_usage.py`
- `test_long_text_handling.py`
- `test_answer_review_schema_provenance.py`
- `test_management_handler_compat.py`

### Files
- `test_review_flow.py`

### Vector DB
- `test_vectors.py`

### Memory
- `test_long_term_memory_service.py`
- `test_chat_exit_service.py`

### Gateway
- `test_metrics_eval_routes.py`
- `test_metrics_routes.py`

### Frontend
- `ChatTab.test.jsx`
- `EvalTab.test.jsx`
- `EvalResults.test.jsx`
- `FilesTab.test.jsx`
- `PipelinePanel.test.jsx`

These are review triggers, not automatic split requirements.

## First step — measure every suite

Before changing tests, collect a repository-wide inventory:

For each suite/domain record:

```text
test files
explicit test functions/cases
collected cases
total runtime
top slowest tests
largest test files
```

Run timing only once per suite unless later edits invalidate it.

Keep detailed outputs in ignored/private artifacts.
Do not paste thousands of test names/dots into the agent transcript.

## Repository-wide test ownership model

Every behavior should have one primary owner:

```text
pure algorithm/math      → unit test
schema/serialization     → contract test
service orchestration    → service/integration test
cross-service message    → producer-consumer contract test
browser workflow         → E2E
historical version       → compatibility lane
```

Higher layers prove wiring; they should not duplicate the full truth table already proven by lower layers.

## Backend lanes

Create clear selectable lanes based on repository structure and/or registered pytest markers.

Recommended logical lanes:

```text
shared
gateway
rag-core
rag-eval
rag-benchmark
rag-metrics
rag-compat
files-core
files-review
embedding
vector
llm-core
llm-provider
llm-compat
memory-core
memory-agent
memory-compat
repo-contract
smoke
```

Do not over-marker every individual test if directory/file structure is already sufficient.

## Frontend lanes

Make frontend tests selectable by feature:

```text
chat
files
eval
metrics
auth
activity
models-config
health
shared-ui
```

Vitest should be able to run one feature without loading unrelated test modules.

Do not add another test runner.

## Split rules

Split a test file when it mixes unrelated stable responsibilities.

Good split:

```text
test_llm_service.py
→ test_llm_execution.py
→ test_structured_output.py
→ test_llm_streaming.py
```

Bad split:

```text
test_llm_service_part1.py
test_llm_service_part2.py
```

Prefer 2–4 cohesive modules over many tiny files.

## Service-specific review requirements

### RAG

Split/reorganize:

```text
test_rag.py
test_eval_runner.py
test_benchmark_runner.py
```

Review for duplicate coverage between:

```text
test_graph_instrumentation.py
test_metrics_facts.py
test_citation_metrics.py
```

and:

```text
test_llm_action_evidence.py
test_benchmark_summary.py
test_benchmark_export.py
test_benchmark_comparison.py
```

and:

```text
test_eval_runner.py
test_retrieval_metrics.py
test_failure_attribution.py
test_golden_set_parser.py
test_retrieval_trace.py
test_eval_store.py
```

Keep compact/high-signal pure tests.

### LLM Agent

Audit `test_llm_service.py` for mixed ownership:

```text
execution
prompt rendering
structured output
provider invocation
streaming
finish reasons
errors
metrics
```

Move truth tables to their canonical lower-level owners.

Do not repeat provider finish-reason truth tables both in provider-specific tests and service-level tests.

Isolate tests for providers that may later be removed:

```text
HuggingFace
Ollama
legacy management/config
```

into compatibility/provider lanes.

### Files

Break `test_review_flow.py` by stable state-machine concerns if useful:

```text
review detection
pause/resume
accept/redact/delete
stale token/hash
transaction/recovery
```

Do not duplicate lower-level DB/patch-map tests at full-flow level.

### Vector DB

Review `test_vectors.py` for mixed:

```text
Qdrant adapter
filters
tenant safety
upsert/delete
legacy envelope normalization
alternate backends
```

Separate Qdrant production contract from compatibility/test-fake behavior.

Security/tenant filter tests stay.

### Memory

Review:

```text
test_long_term_memory_service.py
test_chat_exit_service.py
```

Separate:

```text
write policy
retrieval/ranking
persistence
index sync
LLM extraction/exit
agent behavior
```

Keep false-memory, ownership, destructive-operation and error-semantics coverage.

### Gateway

Review large metrics route suites.

Do not test identical router `try/except` boilerplate dozens of times if error translation becomes centralized.

Keep:

```text
auth
RBAC
CSRF
tenant scope
security startup
route contract
```

high-signal tests.

### Embedding

Suite is already relatively compact.

Do not split just for consistency.

Focus on:

```text
canonical job pipeline
query embedding
model factory
config
health
```

Retire tests only when legacy embedding/extraction production paths are deleted.

### Shared

Generally keep compact security/transport tests.

Do not remove tests for:

```text
auth
rate limiting
RabbitMQ envelope semantics
Kafka lag/backpressure
schema provenance
redaction/logging
```

because they are cheap and high-value.

### Frontend

Review large component tests for overspecified implementation details.

Prefer testing:

```text
visible behavior
user actions
accessibility
API/socket contracts
terminal states
error/loading states
```

Avoid tests that merely assert internal hook calls or DOM structure that is not a product contract.

Split huge feature tests by user workflow, not component internals.

## Compatibility lanes

Create explicit compatibility groupings for tests involving:

```text
legacy
historical
pre-versioning
older schema
old provider
deprecated envelope
old benchmark manifest
old runtime config
```

Rules:

- Keep while the corresponding production compatibility contract is supported.
- Normal feature work should not read/run compatibility tests unless that contract changes.
- When compatibility is retired, delete production compatibility code and tests together.
- Do not preserve obsolete compatibility forever.

## Duplicate-test deletion rule

Delete a test only when at least one is true:

1. corresponding production behavior is deleted;
2. a same/lower-layer test proves the exact invariant and the current test adds no integration/wiring value;
3. the test validates a fake/helper instead of supported production behavior;
4. it asserts implementation detail that is not a contract;
5. the compatibility version is officially retired.

Do not delete tests covering:

```text
security
tenant isolation
recovery
idempotency
transaction semantics
message ordering
citation safety
provenance
redaction
failure classification
schema compatibility still supported
```

without deleting/changing the production contract itself.

## Fixtures

Audit fixture duplication across suites.

Rules:

- Do not create one giant repository `conftest.py`.
- Shared fixture only when truly cross-domain and stable.
- Domain-specific fixtures remain near domain tests.
- Prefer factories/builders with meaningful names over giant fixture graphs.
- Avoid autouse fixtures unless the invariant genuinely applies to every test in that scope.
- Remove fixtures used by zero/one trivial caller when inline setup is clearer.

## Mocking

Review heavy mocking.

Prefer:

```text
fake at the service boundary
```

over:

```text
mock every private method
```

Tests heavily coupled to private implementation should be rewritten toward supported observable contracts when practical.

## Slow tests

Do not assume a large suite is slow.

Measure.

For genuine slow cases:
- identify whether sleep/network/model setup is unnecessary;
- replace real sleeps with events/fake clocks;
- reuse immutable expensive fixtures only when isolation remains safe;
- mark true integration/smoke tests clearly.

Do not remove valuable tests merely to save seconds.

## Test execution policy

### During implementation
Run exact focused tests only.

### Near completion
Run the relevant domain lane.

Examples:

```text
Gateway auth change
→ gateway auth/security tests

Files review change
→ files-review

LLM structured output change
→ llm-core + structured-output tests

Memory agent change
→ memory-agent

Frontend Files change
→ frontend files tests
```

### Cross-cutting/high-risk
Run affected service suite once near completion.

### Full repository
CI/release authority.

Do not run every backend + frontend suite after every narrow task.

## `scripts/ai/check.py`

Update task validation ergonomics so it can target:

```text
focused files
service lane
domain lane
full affected service
```

Requirements:

- successful output remains concise;
- no universal doctor prerequisite;
- broken `.venv` does not block normal validation;
- the isolated uv fallback in `docs/ai/RUNTIME_CONTRACT.md` remains accepted;
- detailed durations/collection output remains private;
- never rerun already-passed broad checks unless later edits invalidate them.

Do not turn `check.py` into a complex test orchestration framework.

## CI

Keep authoritative full backend/frontend suites in CI unless measured CI cost becomes a real problem.

If CI becomes expensive, split jobs by service/feature for parallelism rather than deleting tests.

Full release validation remains broader than task-level validation.

## Mutation sanity check

For each major lane, prove the selection is meaningful.

Use controlled monkeypatch/temp mutation or equivalent validation to demonstrate representative failures are caught by:

```text
rag-core
rag-eval
rag-benchmark
files-review
llm-core
memory-core
gateway
frontend feature lane
```

Do not leave mutations in the worktree.

## Local refactor budget

This task may refactor **test code** across the repository.

It must not perform unrelated production refactors.

Allowed production changes:
- only a genuine defect exposed by the test audit, and only if tiny and directly necessary;
- otherwise report the defect and create/follow the appropriate task.

Avoid:
- giant test helper frameworks;
- arbitrary directory churn;
- thousands of rename-only changes with no selection/readability value.

## Acceptance report

Report before/after by domain:

```text
Backend:
  shared
  gateway
  rag
  files
  embedding
  vector_db
  llm_agent
  memory

Frontend:
  total
  by major feature

Repository smoke/contracts
```

For each:

```text
files before/after
collected tests before/after
runtime before/after
largest file before/after
tests deleted
duplicates removed
compatibility cases moved
```

Also report:

```text
new lanes
lane runtime/count
fixtures removed/centralized
obsolete compatibility tests removed
production files changed
```

No fixed target for total test count.

Success means:
- agents can select/read a much smaller test scope;
- large mixed-responsibility test files are reduced;
- duplicate coverage is lower;
- compatibility is isolated;
- full CI confidence remains intact.

## Validation

1. All affected backend suites.
2. Full backend test matrix once after restructuring.
3. Full frontend test suite once after restructuring.
4. Frontend production build if test/module moves affect imports/config.
5. Root/public-repo tests.
6. Lane-selection sanity tests.
7. Ruff on changed Python test/tool files.
8. `git diff --check`.

Do not run Smoke30/Retrieval220/Full240: this task changes test architecture, not RAG runtime semantics.

Do not commit or push.
