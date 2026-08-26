# DOCS-02 — Evidence-driven README badges and benchmark header

**Branch:** `docs/readme-evidence-badges`

## Goal

Make the top of the public README communicate verified engineering evidence immediately:

- CI health
- supported Python version
- automated test count
- reproducible benchmark identity
- measured RAG quality/performance
- measured tenant-isolation/security evidence

Prefer **evidence over technology-logo clutter**.

## Why this task exists

RAGForge already has a broad technical stack. More framework/logo badges add little credibility. The useful signals are:

```text
Build passes
Tests pass
Benchmark exists
Quality is measured
Security/isolation is measured
```

Do not manually maintain claims such as `40+ automated tests`, benchmark scores, or security results when they can drift or have not been measured.

## Preconditions

This task may be implemented in two stages.

### Stage A — can be done before Baseline V1

Allowed:

- authoritative CI status badge
- Python version badge
- automated test-count generation
- license badge only if the repository actually has a confirmed license
- README structure/placeholders for benchmark evidence

### Stage B — only after BMARK-15 + Baseline V1

Benchmark/security result badges or headline metrics may only be published after a reproducible baseline exists.

Required evidence should include, as applicable:

- dataset version/hash
- Git SHA
- effective configuration
- benchmark summary
- diagnostic ZIP / stored benchmark artifacts
- hardware/runtime metadata

**Never invent or hand-enter benchmark numbers that cannot be traced to a real run.**

## Primary scope

Expected files may include:

```text
README.md
.github/workflows/ci.yml
.github/workflows/<badge-or-readme-metrics-workflow>.yml
scripts/<small test-count or badge-data helper>.py
docs/benchmarks/...
```

Reuse existing CI and Benchmark Center outputs before introducing new infrastructure.

Do not create a separate benchmarking system just for README badges.

## Required README header

Keep the top section concise.

Recommended first-line evidence badges:

```text
CI
Python 3.11
Tests
License
```

Example conceptual layout:

```text
[ CI: passing ] [ Python: 3.11 ] [ Tests: N ] [ License: ... ]
```

Do not add a wall of technology badges such as:

```text
FastAPI
React
Kafka
MongoDB
Qdrant
LangGraph
Docker
```

Those belong in the Tech Stack section.

## CI badge

Use the real GitHub Actions workflow status for `main`.

Requirements:

- points to the authoritative CI workflow
- reflects current `main`
- clicking it navigates to the relevant Actions workflow/run view
- do not create a duplicate workflow solely to obtain a badge

## Python version badge

The badge must derive from or remain consistent with the repository Python source of truth:

```text
.python-version
```

Expected repository version:

```text
3.11
```

Avoid maintaining conflicting version literals.

## Automated test-count badge

### Problem

A manually written claim such as:

```text
40+ automated tests
```

becomes stale quickly.

### Required behavior

Produce the test count from the repository's actual test collection.

The implementation should:

- use the same supported Python/test environment as CI
- collect tests without executing the entire suite
- count tests deterministically
- fail clearly if collection is broken
- avoid generated/temp/private files
- avoid double-counting
- preserve backend/shared/frontend distinction if useful

Preferred evidence model:

```text
Backend tests: N
Frontend tests: M
Total automated tests: N + M
```

or a single stable total if simpler and unambiguous.

### CI integration

The count should refresh automatically through CI or another deterministic repository workflow.

Do not require manual README edits whenever tests are added.

If generating JSON/SVG/static badge data, keep generation deterministic and reviewable.

## Benchmark evidence block

After Baseline V1 exists, add a compact benchmark block near the top of the README.

Example:

```text
Benchmarked on: <GPU / relevant hardware>
Dataset: <document count> docs / <query count> queries
Dataset SHA: <short fingerprint>
Commit: <short Git SHA>
```

Then:

| Metric | Baseline |
| --- | ---: |
| Recall@5 | measured value |
| MRR | measured value |
| nDCG@10 | measured value |
| TTFT p50 | measured value |
| E2E p95 | measured value |
| Success rate | measured value |

Only include metrics the benchmark actually measures reliably.

Do not show `0` for unavailable/unmeasured metrics; use `N/A` or omit them.

## Benchmark badges

After Baseline V1, optionally expose a small subset:

```text
RAG Eval: 240 queries
Recall@5: XX.X%
MRR: 0.XXX
```

Rules:

- values come from a stored reproducible benchmark
- badge source is traceable to the baseline artifact/result
- updating the canonical baseline updates the badge source
- badge values must not silently compare incompatible datasets/configurations
- do not publish candidate/experimental run numbers as the public baseline

Prefer a few meaningful badges over many metrics.

## Security / tenant-isolation evidence

Only after a real adversarial isolation benchmark exists, expose measured evidence such as:

```text
Cross-tenant leakage: 0 / N
```

or:

```text
Tenant isolation: N/N unauthorized attempts blocked
```

Requirements:

- `N` is the actual executed attempt count
- run is reproducible
- result is tied to a Git SHA/build
- no secret values or private document content appear in README artifacts
- do not publish before the adversarial benchmark exists

A claim like `Zero cross-tenant leakage` without a denominator and reproducible test is not acceptable.

## Agent benchmark evidence

Do not add an Agent-success badge until `AGENT-03` provides a real evaluation harness.

When available, useful metrics may include:

```text
Agent task success
Invalid tool-call rate
Unnecessary mutation rate
Prompt-injection success rate
```

Do not create these numbers manually.

## Data provenance

Every published benchmark result should be traceable to:

```text
baseline/candidate identity
dataset id/version/hash
Git SHA
effective retrieval configuration
embedding model
LLM model
hardware/runtime metadata
timestamp
```

Where possible, link from the README benchmark block to benchmark methodology/results documentation.

Do not expose private diagnostic artifacts.

## README claim cleanup

While editing the README, audit nearby claims for consistency with current implementation.

In particular:

- use `Production-oriented` or similarly defensible wording unless production gates are truly satisfied
- do not claim real CrossEncoder reranking before RAG-04 exists
- do not claim true hybrid dense+sparse retrieval before RAG-05 exists
- use the actual application-service count
- distinguish Implemented / Experimental / Planned where useful

Do not turn this task into a broad README rewrite.

## Badge implementation constraints

- No secrets/tokens embedded in badge URLs or generated files.
- No external write credentials merely to update a badge.
- Prefer GitHub-native workflow badges or repository-generated static data.
- Do not introduce third-party SaaS unless clearly justified.
- Badge generation failure must not hide test failures.
- Avoid workflows that create commit loops on `main`.
- Do not bypass branch protection to update generated badge files.

## Acceptance criteria

### Stage A

- README shows authoritative CI status.
- README shows Python 3.11 consistently with `.python-version`.
- Automated test count is generated from actual test collection rather than maintained by hand.
- Test-count generation is deterministic and documented.
- No technology-logo badge wall is added.
- No unverified benchmark/security numbers appear.

### Stage B

- README contains a compact Baseline V1 evidence block.
- Every published benchmark number is traceable to a real stored benchmark run.
- Dataset identity and Git/build identity are visible or linked.
- Missing metrics are not represented as zero.
- Security/agent badges appear only if corresponding reproducible evaluations exist.
- Replacing the canonical baseline has a defined procedure for refreshing public metrics.

## Validation

Use focused validation only.

### README / badge generation

Verify:

- Markdown renders correctly
- CI workflow badge targets the correct workflow/branch
- generated badge/test-count files are deterministic
- no broken relative links
- no secrets in generated content

### Test count

Run collection/count logic twice and verify identical output.

If collection fails:

```text
FAIL
```

Do not publish a previous/stale count as current.

### Benchmark values

For each public baseline metric:

- compare README value to the authoritative baseline summary/artifact
- verify dataset hash/version
- verify Git SHA
- verify effective config compatibility

No full backend/frontend suite is required solely for README edits unless helper/CI code changes make it necessary.

GitHub CI remains authoritative for broad validation.

## Out of scope

Do not implement in this task:

- new RAG evaluation metrics
- Pass-2 fixes
- CrossEncoder reranking
- hybrid retrieval
- Agent evaluation harness
- adversarial isolation harness
- Benchmark Center redesign
- a new benchmarking backend
- generic technology/logo badges
- fake performance/security claims

This task **surfaces existing verified evidence**; it does not manufacture evidence.

## Task rules

- Follow root/scoped `AGENTS.md` and `CLAUDE.md`.
- Inspect current README/workflows/benchmark outputs before editing.
- Reuse existing CI and Benchmark Center artifacts.
- Current implementation wins over stale assumptions.
- Keep this branch limited to evidence-driven README presentation.
- Do not commit or push.
- If Baseline V1 does not yet exist, complete Stage A only and explicitly report Stage B as deferred.

## Suggested commit

**Title:**

`docs: add evidence-driven README badges and benchmark summary`

**Description:**

- surface authoritative CI, Python and automated-test evidence in the README
- generate test-count claims from repository test collection instead of manual text
- add a reproducible Baseline V1 benchmark summary when verified results are available
- keep performance, security and agent claims gated on measured evidence
