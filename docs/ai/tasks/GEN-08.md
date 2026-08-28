# GEN-08 — Freeze accepted GEN-07 runtime

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
- Use the canonical runtime/tooling from `docs/ai/RUNTIME_CONTRACT.md`.
- Do not weaken tests, mypy, Ruff, auth, security, or benchmark gates just to make them pass.
- Stop on any new unrelated failure and report it.


## Files to inspect
- `docker-compose.yml`
- `.env.example`
- RAG benchmark runtime/provenance config
- relevant operator docs

## Required persisted runtime
```text
VLLM_IMAGE=vllm/vllm-openai:v0.27.1
VLLM_USE_V2_MODEL_RUNNER=0
VLLM_GPU_MEMORY_UTILIZATION=0.85
VLLM_MAX_MODEL_LEN=10240
VLLM_MAX_NUM_SEQS=4
VLLM_MAX_NUM_BATCHED_TOKENS=2048
VLLM_PERFORMANCE_MODE=interactivity
LLM_REQUEST_PREFETCH=4
```

Ensure Compose passes:
```text
--max-num-batched-tokens 2048
--performance-mode interactivity
```

## LOCAL TEST 1 — RUN BY CODEX
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
docker compose config
```

Verify rendered `vllm` command and RAG provenance env.

## LOCAL TEST 2 — RUN BY CODEX
If necessary, recreate only vLLM/RAG to verify persisted config:
```powershell
cd "C:/Users/vital/Desktop/AgentAPP/ragapp-public"
docker compose up -d --force-recreate vllm rag
docker compose ps
```

Verify:
- image 0.27.1
- V1
- GPU 0.85
- model len 10240
- max seqs 4
- batched tokens 2048
- performance mode interactivity

## LOCAL TEST 3 — RUN BY CODEX
- `/health`
- `/version`
- existing representative vLLM warmup twice until no JIT contamination
- one tiny completion

## DO NOT RUN
- Smoke30
- Retrieval220
- Full240
- new performance sweep

## STOP CONDITION
Persisted Compose defaults equal the accepted GEN-07 winner.
