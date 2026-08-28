# BMARK-15C — Benchmark provenance completeness and strict comparison compatibility

**Branch:** `fix/benchmark-provenance-compatibility`

## Goal

Make benchmark comparison refuse false compatibility when critical runtime provenance is unknown, and make the benchmark manifest capture enough real build/runtime identity for Baseline V1.

## Problem

Two manifests can currently contain the same unknown values, for example:

```json
{
  "embedding": {
    "model": null
  }
}
```

and a naive equality comparison can treat them as compatible.

But:

```text
unknown == unknown
```

does not prove that two runs used the same embedding model.

It means compatibility is unknown.

## Required compatibility semantics

Introduce explicit compatibility states or equivalent logic:

```text
compatible
incompatible
unknown
```

At minimum:

- known equal values -> compatible for that field;
- known different values -> incompatible;
- critical field missing/unobserved on either side -> unknown.

The whole run comparison must not claim strong compatibility if a critical field is unknown.

### Critical provenance fields

Inspect current manifest schema and use the existing allowlist.

At minimum Baseline-ready evidence should cover, where the running stack can observe it:

```text
build.git_sha
build.git_branch
build_timestamp
image_tag

embedding model
embedding vector size

chunk size
chunk overlap
chunk strategy

vector store type
vector collection

LLM chat model
LLM max model length
quantization if observable

retrieval strategy
context_k
eval_candidate_k
Pass2 active/effective
reranker implementation/model if active
hybrid strategy if active
```

Do not report legacy compatibility booleans as active capability unless active runtime behavior proves they are in use.

## Build provenance

Wire real immutable build identity into the RAG benchmark runtime.

Preferred source:

```text
RAGFORGE_GIT_SHA
RAGFORGE_GIT_BRANCH
RAGFORGE_BUILD_TIMESTAMP
RAGFORGE_IMAGE_TAG
```

Use the repo's existing manifest environment allowlist.

Do not shell out to Git from inside a production container if explicit build/env injection can provide the immutable value.

### Docker/Compose

If needed, add build args/env plumbing so the running RAG service receives actual build provenance.

Do not expose secrets.

## Runtime provenance

Prefer effective runtime values over stale configuration defaults.

Examples:

- vLLM model/max model len should represent the served runtime when observable.
- reranker should be reported inactive if the implementation is only score sort/dedupe.
- hybrid should be reported inactive while retrieval is dense-only.

Unknown remains:

```json
null
```

plus `unobserved` evidence.

Never invent.

## Comparison behavior

For every critical field, comparison output should explain:

```text
field
left value
right value
status: same | different | unknown
reason
```

The comparison result must distinguish:

```text
safe apples-to-apples comparison
known incompatible comparison
compatibility cannot be proven
```

Do not suppress useful metric deltas entirely when compatibility is unknown, but visibly mark them as non-authoritative/non-comparable.

## Non-goals

Do not:

- change quality metrics;
- change retrieval/generation behavior;
- tune vLLM;
- change Golden Set labels;
- implement BMARK-15A accounting;
- implement BMARK-15B latency.

## Required tests

At least:

1. known equal critical field -> same.
2. known different critical field -> incompatible.
3. left null/right null -> unknown, not same.
4. left known/right null -> unknown.
5. `unobserved` critical field -> unknown.
6. non-critical unknown field does not necessarily block all comparison.
7. comparison result cannot be `compatible=true` when a required critical field is unknown.
8. real Git SHA is captured when injected.
9. absent Git SHA remains null/unobserved.
10. inactive legacy reranker/hybrid flags are not reported as active effective strategy.
11. manifest remains secret-safe.
12. historical manifest schema remains readable.

## Validation

Doctor once.
Focused benchmark manifest/comparison tests.
Ruff changed files.
Docker/Compose config validation if build/env plumbing changes.

If RAG typed config changes in normal mypy scope, run mypy according to policy.

Run RAG affected suite once near completion if runtime/provenance contracts change materially.

## Manual acceptance

Perform two small Smoke30-compatible comparisons.

### Same/Same known provenance

Same build/config:

```text
expected: compatible
```

### Unknown provenance

Deliberately omit one critical build/runtime value in a disposable environment:

```text
expected: compatibility unknown
NOT compatible
```

No Full240.

## Final report

Return:

1. critical compatibility field list;
2. comparison state model;
3. provenance fields now captured;
4. Docker/runtime injection changes;
5. tests;
6. manual same/same + unknown checks still required.

Do not commit or push.
