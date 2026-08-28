# Streaming output safety

RAG answer tokens are fail-closed. Generation deltas remain inside the RAG
process until the complete candidate answer passes the output risk scan. A
blocked candidate emits no `token` events; only the configured safe replacement
is returned in the terminal `done` event. If extended mode generates a revision,
the revision replaces the earlier draft before approval.

`rag_ttft_seconds` now measures time from turn start to the first **approved,
user-visible** token. It includes generation, evaluation/revision, and output
safety latency. Blocked turns have no TTFT observation and store `ttft_ms: null`.
The approved-token flush is bounded by
`approved_stream_emit_timeout_seconds`; cancellation propagates to the flush and
no background emission continues after the turn ends.
