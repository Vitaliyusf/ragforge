# RAG-01 — Fix Pass2 global ranking

## Execution location

**RUN BY:** Codex locally on the user's machine.

**REPOSITORY ROOT:**
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
```

## Global rules

- Do not reset, stash, clean, revert, or switch branches.
- Do not commit or push unless explicitly requested.
- Inspect current code before editing.
- TEST WHAT CHANGED. LET CI TEST THE REPOSITORY.
- Use the repository's canonical Python 3.11 test toolchain.
- Do not weaken tests, mypy, Ruff, auth, security, or benchmark gates just to make them pass.
- Stop on any new unrelated failure and report it.


## Files to inspect
- `backend/rag/app/services/conversation_graph.py`
- `backend/rag/app/tests/test_rag.py`
- retrieval/ranking tests found by search

## DISCOVERY — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
rg -n "pass_two|pass2|rerank|dedupe|ranking|retrieve_pass_two" backend/rag/app/tests backend/rag/app/services
```

## Required behavior
Pass1 + Pass2 candidates must be globally deduped/ranked before final Top-K.

## LOCAL FOCUSED TEST — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public/backend/rag"
$env:PYTHONPATH="$PWD;$PWD\.."
pytest app/tests -q -k "pass_two or pass2 or ranking or rerank or dedupe"
```

## LOCAL FULL RAG SUITE — RUN BY CODEX
```powershell
pytest app/tests -q
```

## LOCAL DOCKER BENCHMARK 1 — RUN BY CODEX
Smoke30 / `smoke_quality`

Gate:
```text
28 success
2 expected guardrails
0 failed
0 timeout
0 evaluator failures
0 evaluator length
```

## LOCAL DOCKER BENCHMARK 2 — RUN BY CODEX
Only if Smoke30 passes:
Retrieval answerable220.

Compare:
- MRR
- Recall@5
- Hit@1
- Pass2 diagnostics

## DO NOT RUN
Full240.

## STOP CONDITION
Smoke30 clean and Retrieval220 shows no material regression.
