# Migration from V2 to V3

## Completed
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

## Absorbed / retired
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

## Policy change
Dedicated large-file refactor tasks are no longer the default. Every behavior task owns a bounded local refactor budget for the concern it changes. Standalone cleanup remains only for residual cross-cutting ownership or lifecycle work.