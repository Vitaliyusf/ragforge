# Service executor budgets

`CONC-02` owns the synchronous RabbitMQ handler boundary. The values below are
defaults and may be overridden through each service's normal settings source.
Admission waits for at most `executor_submit_timeout_seconds` (default 1s),
then raises the typed `ExecutorOverloaded` error. Lifespan stops consumers
before draining and shutting down the owned pool.

| Service | RabbitMQ prefetch | Executor workers | Executor queue bound | Downstream max concurrency | Expected overload behavior |
| --- | ---: | ---: | ---: | ---: | --- |
| files | 1 | 1 | 0 | 1 synchronous repository handler | bounded wait, then typed overload |
| vector_db | 1 | 1 | 0 | 1 vector-store RPC operation | bounded wait, then typed overload |
| embedding query RPC | 1 | 1 | 0 | 1 model query | bounded wait, then typed overload |
| memory | 10 | 10 | 0 | 10 synchronous request handlers; outbound RPC remains capped at 32 | bounded wait, then typed overload |
| llm_agent | 4 primary + 1 per six auxiliary queues (10 total) | 10 | 0 | `max_concurrent_requests` (10) | bounded wait, then typed overload |

The LLM pool bounds handler entry only. Provider scheduling remains owned by
`CONC-03`; this boundary does not add a nested provider pool.
