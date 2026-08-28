# GEN-05 — Optional post-generation LLM call reduction

**Branch:** `perf/post-generation-review`

**Status:** OPTIONAL — execute only if GEN-01..04 do not reduce benchmark/serving latency enough.

## Goal

Reduce the number of sequential LLM calls after answer generation without weakening safety or degrading quality evidence.

## Current regular path

Conceptually:

```text
generate answer
    ↓
answer evaluation
    ↓
output risk scan
    ↓
persist / done
```

Both `answer_evaluation` and `content_risk_scan` consume LLM inference.

The evaluator already returns quality/safety-oriented fields, but it is not automatically equivalent to the output safety policy.

This task must prove any consolidation is safe.

## Allowed design directions

Choose one only after inspecting the current implementation and measurements.

### Option A — Combined post-generation structured review

Create a structured action that returns:

```text
quality review
claims
groundedness/completeness
hallucination verdict

+
output safety decision
blocked
safe replacement if policy requires one
```

### Option B — Move non-user-visible quality evaluation off the critical path

If Regular `answer_evaluation` does not change the user-visible answer, consider:

```text
critical path:
generation
→ output safety
→ user response

async/benchmark path:
answer evaluation
→ quality metrics
```

This changes observability timing and must preserve the benchmark's ability to wait for evaluation when explicitly running quality eval.

Do not choose Option B if downstream product behavior requires synchronous review.

## Safety requirement

This task is unacceptable unless output safety parity is demonstrated.

Required targeted suites:

```text
PromptInjection8
Unanswerable20
```

plus any existing guardrail-focused tests.

If there is an existing adversarial safety corpus, include it.

A quality speedup cannot justify weaker safety.

## Streaming requirement

Do not worsen the known fail-closed streaming problem.

If output tokens are currently visible before final safety validation, do not claim this task fixes that unless it actually does.

Do not combine SAFE-01 into this PR.

## Required measurements

Before/after:

```text
number of LLM calls per Regular turn
Regular phase wall-clock
generation latency
post-generation latency
guardrail block decisions
false-positive/false-negative safety cases
groundedness
citation precision/recall
hallucination rate
structured parse failures
```

## Non-goals

Do not:

- change retrieval;
- implement CrossEncoder/hybrid;
- change the base model;
- combine SAFE-01;
- change agent behavior;
- run Full240 until targeted tests pass.

## Required tests

Depends on selected design, but must include:

1. same benign answer reaches user.
2. output guardrail still blocks unsafe output.
3. quality review remains available for benchmark runs.
4. no duplicate user-visible answer emission.
5. timeout/error path remains bounded.
6. structured output failure is explicit.
7. background evaluation, if used, cannot mutate already-sent answer.
8. benchmark can still await quality review deterministically.
9. historical metrics semantics remain documented.

## Validation

Doctor once.
Focused RAG + llm_agent tests.
Run affected suites once near completion for both services.

## Manual acceptance

Run:

```text
Smoke30 Regular
PromptInjection8
Unanswerable20
```

Only if those pass with safety/quality parity may a Full240 Full Quality run be justified later.

## Final report

Return:

1. selected design and why;
2. calls removed from critical path;
3. before/after wall-clock;
4. safety parity results;
5. quality parity results;
6. known limitations;
7. explicit statement whether SAFE-01 remains open.

Do not commit or push.
