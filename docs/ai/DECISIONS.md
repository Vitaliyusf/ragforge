# Durable Architecture Decisions

These decisions prevent agents from repeatedly reopening settled architecture without evidence.

1. **Use current infrastructure before adding platforms.**
   No Redis/Celery/Temporal/Elasticsearch/Kubernetes/Terraform solely for resume value.

2. **RabbitMQ and Kafka have different roles.**
   RabbitMQ is RPC; Kafka is durable async pipeline/events.

3. **RAG tracing is extended, not duplicated.**
   Existing execution trace/checkpoints are the base for diagnostic retrieval tracing.

4. **Golden truth is eval-side.**
   Expected file/chunk/fact labels must not alter production retrieval behavior.

5. **Measure before optimizing.**
   Retrieval, reranking, hybrid search, async persistence and vLLM tuning require reproducible before/after evidence.

6. **At-least-once + idempotency over fake exactly-once.**
   Durable messaging correctness comes from event IDs, unique keys/deterministic vector IDs and commit semantics.

7. **Self-hosted token API charge is not compute cost.**
   `$0 API token charge` must not be presented as zero GPU/compute cost.

8. **Security scope is server-side.**
   Tenant/user scope cannot be chosen by client JSON, model tool args or document content.

9. **Pure functions stay functions.**
   OOP is used for state/lifecycle/policy/repository/resource ownership, not as a blanket style rule.

10. **One behavior change per branch.**
    Large behavior-neutral refactors are separated from algorithm changes whenever practical.
