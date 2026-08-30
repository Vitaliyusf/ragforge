# MEMORY-AGENT-01 LangMem comparison spike

Date: 2026-08-30

Decision: `CUSTOM POLICY KEPT`

## Runtime result

The canonical Memory service image was inspected without installing or changing
dependencies:

```text
langmem_installed=False
langchain_installed=False
langgraph_installed=False
```

An executable custom-vs-LangMem Qwen comparison is therefore not authoritative
in the current runtime. Installing LangMem only for this task would introduce
LangChain, LangGraph, and TrustCall into a service whose canonical dependency
layer currently has none of them, and would violate the repository rule against
ad-hoc dependencies used to manufacture a result.

## Primitive comparison

Primary sources inspected:

- LangMem reference: https://langchain-ai.github.io/langmem/reference/
- LangMem extraction implementation: https://github.com/langchain-ai/langmem/blob/main/src/langmem/knowledge/extraction.py
- LangMem memory tools implementation: https://github.com/langchain-ai/langmem/blob/main/src/langmem/knowledge/tools.py
- LangMem background guide: https://github.com/langchain-ai/langmem/blob/main/docs/docs/background_quickstart.md

| Concern | LangMem primitive | RagForge requirement/result |
|---|---|---|
| Extraction and consolidation | `create_memory_manager` supports structured schemas, inserts, updates, and optional deletes | Useful conceptual match, but RagForge needs separate deterministic business validation and canonical Memory V2 writes |
| Stateful background memory | `create_memory_store_manager` and `ReflectionExecutor` search and persist through LangGraph `BaseStore` | Persistence ownership conflicts with MongoDB canonical state and Qdrant-derived indexing unless a new adapter/service boundary is built |
| Hot-path tools | `create_manage_memory_tool` and `create_search_memory_tool` expose create/update/delete/search over a LangGraph store | Too much mutation authority for the chat model; RagForge requires server-bounded ids and explicit delete authorization |
| Delete safety | LangMem defaults extraction deletes off, but store phases/tools can enable delete | RagForge keeps delete off for background chat exit and validates authorization plus candidate membership deterministically |
| Structured output | LangMem uses Pydantic schemas and TrustCall extraction | The existing typed llm_agent already supplies provider JSON-schema transport and Pydantic validation without another control plane |
| Local vLLM/Qwen | LangMem accepts a model string or `BaseChatModel`; official examples use provider/LangChain model initialization | Not executable in the canonical image; no claim is made about Qwen reliability, Hebrew quality, latency, or token cost |
| Hebrew/mixed language | No repository-local executable evidence | Kept in the deterministic scenario surface; model-quality measurement remains unverified |

## Hot path versus background

RagForge keeps background chat-exit curation. It avoids adding model latency to
the user-visible answer path and fits the existing Memory-owned exit workflow.
The trade-off is that explicit “remember/forget” UX cannot be confirmed during
the same turn. A future hot-path product command may call the same bounded
policy, but it must supply explicit product authorization for destructive
actions and still delegate persistence to `LongTermMemoryService`.

## Adoption threshold

LangMem should be reconsidered only if an isolated, canonical-runtime spike can
show a measurable correctness or maintenance benefit on the committed scenario
suite, including Hebrew/mixed input and local vLLM/Qwen structured-output
reliability. Even then, only stateless extraction/consolidation could be adopted;
MongoDB/Qdrant ownership, tenant scope, action validation, authorization, and
observability remain RagForge responsibilities.

No LangMem, LangChain, LangGraph, TrustCall, PydanticAI, CrewAI, or LlamaIndex
dependency was added.
