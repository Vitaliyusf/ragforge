# BMARK-13A — Explicit guardrail outcomes

**Branch:** `fix/eval-guardrail-outcomes`

## Goal
Represent intentional guardrail decisions as explicit eval/benchmark outcomes instead of generic conversation-graph failures.

## Problem
A successful `content_risk_scan` that intentionally blocks a request currently reaches the generic graph exception path. This makes a safety decision look like an application failure and corrupts benchmark accounting.

## Scope
- conversation guardrail outcome contract
- eval per-item outcome normalization
- benchmark summary/failure accounting where needed
- structured logging
- focused tests

## Required behavior
Distinguish, using the smallest project-consistent schema:

```text
success
guardrail_blocked
failed
timed_out / timeout if already supported
unscorable/skipped where already supported
```

For a block, persist enough structured evidence to identify:

```text
outcome = guardrail_blocked
guardrail_stage = input | output
```

Do not persist raw sensitive prompt text merely to classify the block.

Intentional blocks must not emit the same ERROR-level `conversation graph execution failed` event used for unexpected exceptions. Prefer structured INFO/WARN with `outcome=guardrail_blocked` and the stage.

`guardrail_blocked` is an observable outcome, not automatically a benchmark PASS. Do not invent an expected-outcome scoring policy here.

Blocked items must not enter generation-dependent denominators when generation never ran.

## Non-goals
- no safety bypass/weakening
- no retrieval/ranking/context changes
- no progress UI
- no crash recovery
- no security scoring framework

## Required tests
1. Input block -> `guardrail_blocked`.
2. Output block is distinguishable if reachable through eval.
3. Block is not stored as generic graph/application failure.
4. Block does not use generic graph-crash logging.
5. Unexpected graph exception still remains an error.
6. Summary separately reports blocked vs failed.
7. Denominators remain honest for input-blocked items.
8. Historical rows without the new field remain readable.

## Validation
At task start:

```powershell
python scripts/ai/check.py doctor
```

Then focused tests + Ruff changed files. Because this changes eval/result contracts, run the RAG affected-service suite once near completion. Mypy only if changed typed contracts are in normal CI scope.

## Manual gate
Run Smoke30 after merge. Acceptance is:

```text
all 30 items accounted for
guardrail blocks separate from real failures
actual application/infrastructure failures = 0 for a healthy run
```

Do not publish Smoke30 metrics.

## Final report
Return design, changed files, logging/accounting behavior, test counts, and deferred work. Do not commit or push.
