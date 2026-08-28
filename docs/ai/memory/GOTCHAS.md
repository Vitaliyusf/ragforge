# High-Value Gotchas

- **Eval K:** production `top_k_documents` and eval candidate depth differ. Recall@20 requires at least 20 observable candidates.
- **Reranker naming:** dedupe/sort by existing score is not a learned CrossEncoder reranker.
- **Hybrid naming:** dense Qdrant search alone is not hybrid lexical/sparse+dense retrieval.
- **Ground truth:** golden labels never enter live production retrieval.
- **Prometheus scope:** do not assume operational Prometheus series are tenant-scoped because Mongo turn facts are.
- **Prometheus labels:** never add tenant/run/file/chunk/trace identifiers.
- **Mongo transactions:** a contextmanager cannot replay caller code by yielding a second time after failure.
- **Async:** `time.sleep()` / sync PyMongo on async hot paths can stall unrelated requests.
- **Frontend abort:** ignoring a stale Promise is not fetch cancellation; AbortSignal must reach `fetch`.
- **Streaming React:** token-by-token large Context/reducer updates can create hundreds of renders/state clones.
- **Browser writes:** browser callbacks should not be the authoritative mechanism for distributed persistence correctness.
- **Memory agent:** user/document text is untrusted; tool mutation authorization must be server-side.
- **README:** public docs may lag code. Verify executable behavior.
- **Capability ownership:** search capability records, symbols and callers before adding an implementation; one capability has one authoritative path.
- **Configuration honesty:** accepted configuration must change real implemented behavior; fail unsupported updates explicitly.
- **Compatibility:** migrate callers and delete legacy code; temporary dual paths require a removal condition and tracking task.
- **Validation environment:** `doctor` is diagnostic, not universal; a broken `.venv` does not block direct isolated `uv` Python 3.11 validation.
- **Test count:** raw test count is not a quality target; select focused/domain tests and keep supported historical behavior in a compatibility lane.
