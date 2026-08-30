# Memory task update — framework/ecosystem review

Updated tasks after reviewing RagForge against LangGraph, LangSmith, LangMem,
PydanticAI, Zep, Mem0, LlamaIndex, CrewAI and adjacent agent/memory tooling.

## Incorporated

- Replace current SHA256/128 pseudo-memory vectors with the existing
  `intfloat/multilingual-e5-small` / 384-dim Embedding service path.
- Use LangGraph Store concepts as an architectural reference for Memory V2
  namespaces, keys, metadata and bounded search without replacing Mongo/Qdrant.
- Add temporal validity/supersession/current-truth semantics inspired by Zep.
- Add a bounded LangMem comparison spike before finalizing Memory Agent policy.
- Add PydanticAI-style separation of schema validation, business validation,
  action validation and retry budgets.
- Add LangSmith AgentEvals/OpenEvals-style trajectory evaluation.
- Separate memory generation, persistence/lifecycle, retrieval, agent-use and
  final-response evaluation stages.

## Explicitly not adopted as core runtime dependencies

- LangChain
- LlamaIndex
- CrewAI
- Haystack
- Mem0
- Zep
- PydanticAI

LangMem may be partially adopted only if the MEMORY-AGENT-01 comparison shows a
measurable correctness or maintainability win while preserving RagForge-owned
persistence and authorization boundaries.
