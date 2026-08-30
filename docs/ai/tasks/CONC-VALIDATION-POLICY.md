# CONC-VALIDATION-POLICY — Minimal validation for the concurrency track

## Rule

Do **not** run broad validation on every task.

The concurrency track uses:

```text
implementation task
→ smallest focused regression proving the changed behavior
→ Ruff on changed Python files
→ git diff --check
→ STOP
```

No full service suite, no repository-wide pytest, no broad mypy, no Docker rebuild, and no load benchmark on ordinary implementation tasks unless that task explicitly owns one of those checks.

## Per-task validation budget

For ordinary implementation tasks:

1. Run only tests directly covering the touched behavior.
2. Prefer one focused test command; two only when the change crosses two real owners.
3. Run Ruff only on changed Python files.
4. Run `git diff --check`.
5. Run narrow mypy only when the changed code introduces/changes a typed public contract and a concrete type failure is plausible.
6. Stop.

Do not rerun already-green suites from previous tasks.

## Milestone checkpoints

Broad validation happens only at these checkpoints:

### CHECKPOINT A — after CONC-02
Transport + executor foundation.

Run:
- affected shared/transport focused suites;
- one integration smoke for RPC;
- no full repository suite.

### CHECKPOINT B — after CONC-05 + VECTOR-02
Model/retrieval concurrency foundation.

Run:
- embedding focused suite;
- llm_agent focused suite;
- reranker/retrieval focused suite;
- vector focused suite;
- one small concurrency benchmark.

### CHECKPOINT C — after CONC-07 + CONC-08 + CONC-06
Memory / file I/O / RAG DAG.

Run:
- affected Memory benchmark once;
- one upload/ingestion smoke;
- one chat/RAG smoke.

### CHECKPOINT D — after CONC-09 + CONC-10
Pipeline + process topology.

Run:
- ingestion ordering/idempotency smoke;
- worker/process scale smoke;
- no full repo suite.

### FINAL — CONC-99
This is the only task that owns the full authoritative validation and final load evidence.

Run:
- all affected backend service suites;
- frontend suite if CONC-11 changed frontend;
- canonical mypy;
- Ruff;
- Docker/Compose validation;
- authoritative retrieval benchmark;
- Memory 624 benchmark;
- final concurrency/load benchmark;
- final diff-check.

## Environment rule

If Docker or a live runtime is unavailable during a normal implementation task:

- do not block the task unless the changed behavior can only be validated live;
- finish deterministic/focused validation;
- defer the live proof to the next milestone or `CONC-99`.

## Stop rule

Once the focused regression for the changed behavior is green, stop. Do not spend tokens proving unrelated code again.
