# RAGForge Backend Instructions

Applies to `backend/**`.

- Python 3.11 is the current CI/runtime baseline until an explicit upgrade task changes it.
- Prefer typed boundaries: Pydantic for transport/config; Protocol/ABC only when a real substitutable contract exists.
- Keep async request paths non-blocking. Use async clients or deliberate bounded offload for sync work.
- Lifespan owns clients, pools, consumers, executors and shutdown. Avoid new module-global runtime singletons.
- Mongo queries/writes must preserve trusted tenant/owner scope and appropriate indexes.
- Kafka durable workflows target at-least-once + idempotency; do not claim exactly-once without evidence.
- RabbitMQ remains RPC and Kafka durable pipeline/events unless an explicit decision changes this.
- Do not duplicate envelope/auth/retry/logging infrastructure that belongs in `backend/shared`.
- Run the touched service test suite; use `docs/ai/TESTING.md`.
