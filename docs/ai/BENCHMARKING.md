# Benchmarking and Measurement Rules

## Reproducibility
For before/after comparisons hold constant when possible:
- dataset/version/hash
- Git/config except the intended variable
- model and model flags
- chunking/index
- hardware/GPU
- concurrency/workload
- warmup and measured sample counts

Record unknown values as `null`.

## Retrieval quality
Use existing golden-set/eval infrastructure.
Core metrics:
- Recall@1/3/5/10/20
- Precision@K / Hit@K
- MRR
- nDCG@5/10
- empty-retrieval rate
- evaluated/skipped/stale/error counts

Candidate depth must be >= the largest K reported.

## Answer quality
When available:
- groundedness
- completeness
- expected-claim coverage
- citation precision/recall
- claim count
- supported/unsupported count and rate
- judge model/prompt/config metadata

LLM-judge results must be labelled as judge-evaluated proxies.

## Performance
Report:
- sample count
- mean
- min/max
- p50/p95
- p99 only when sample count makes it meaningful
- throughput/request rate
- error/timeout/retry count

Stages where available:
TTFT, rewrite, embedding, retrieval, pass2, rerank, generation, evaluation, persistence, total.

## Typical protocol
Latency benchmark:
- ~20 warmups + ~100 measured requests when affordable.
- Expensive LLM benchmark: at least ~10 warmups + 30–50 measured requests.
- Use the same ordered workload for baseline/candidate.

## Decision rule
Do not state "X improved performance/quality" without actual before/after evidence.
Code correctness can be accepted without a performance claim.
