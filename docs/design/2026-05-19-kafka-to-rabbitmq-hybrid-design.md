# Design: Kafka → RabbitMQ Hybrid Migration

**Date:** 2026-05-19  
**Status:** Approved  
**Scope:** Replace Kafka with RabbitMQ for all request/reply (RPC) flows. Keep Kafka for the embedding event pipeline.

---

## Problem

All inter-service messaging currently runs over Kafka, including synchronous request/reply flows where the gateway waits for a response. This forced a manual RPC layer: a shared `gateway.replies` topic, a `RequestResponseMatcher` (correlation-ID → asyncio.Future map), and a `GatewayKafkaReplyRouter` background thread. ~300 lines of plumbing to simulate something RabbitMQ does natively.

Kafka is the right tool for the embedding pipeline (durable, replayable, ordered event stream) but the wrong tool for transient RPC calls.

---

## Decision

**Hybrid architecture:**

| Transport   | Used for |
|-------------|----------|
| RabbitMQ    | All gateway ↔ service request/reply flows |
| Kafka       | Embedding event pipeline only (`embedding.jobs.*`, `vector_db.upsert.*`) |

**RabbitMQ client:** `aio-pika >= 9.4` (native async, FastAPI event loop compatible).  
**Refactor depth:** Deep — use native RabbitMQ RPC, delete the matcher/router entirely.

---

## Architecture

### Exchange Topology

One `direct` exchange: `ragapp.requests`

Each RPC service declares one **durable** queue bound with `routing_key = service_name`:

| Queue name           | Routing key         | Service   |
|----------------------|---------------------|-----------|
| `files`              | `files`             | files     |
| `memory`             | `memory`            | memory    |
| `llm_agent`          | `llm_agent`         | llm_agent |
| `rag`                | `rag`               | rag       |
| `vector_db`          | `vector_db`         | vector_db |
| `embedding`          | `embedding`         | embedding |
| `model_management`   | `model_management`  | llm_agent |
| `config_management`  | `config_management` | llm_agent |

### Native RPC Flow

```
Gateway                           Service (e.g. memory)
───────────────────────────────   ─────────────────────────────
1. declare exclusive auto-delete
   reply queue (per-request)

2. publish to ragapp.requests
   routing_key = "memory"
   reply_to    = reply_queue.name
   correlation_id = uuid4()
                              →   3. consume from "memory" queue
                                  4. process request
                                  5. publish reply to default exchange
                                     routing_key = reply_to value
                              ←
6. async for on reply queue
   receives single message
   queue auto-deletes
```

**Deleted infrastructure:**
- `gateway/app/core/kafka_reply_router.py`
- `gateway/app/core/request_matcher.py`
- `gateway/app/core/kafka_client.py`
- `gateway.replies` Kafka topic

### Kafka Pipeline (unchanged)

```
files service
  └─► embedding.jobs.requested (Kafka)
        └─► embedding service
              ├─► vector_db.upsert.requested (Kafka)
              │     └─► vector_db service
              └─► embedding.jobs.completed (Kafka)
              └─► files.requests stage-update (Kafka → files service)
```

---

## Components

### `shared/rabbitmq_base.py` (new)

Replaces `shared/kafka_base.py` for RPC services. `kafka_base.py` stays — embedding pipeline uses it.

```python
class RabbitMQSettings(Protocol):
    rabbitmq_url: str              # amqp://guest:guest@rabbitmq:5672/
    rabbitmq_exchange: str         # ragapp.requests
    rabbitmq_queue: str            # service queue name
    rabbitmq_prefetch_count: int   # default 1 (process one at a time)

class BaseRabbitMQConsumer:
    """Async consumer. No threads. Integrates with FastAPI lifespan.
    Auto-acks on success, nacks with requeue=False on exception (→ DLQ).
    """
    async def start(self, handler: Callable[[dict, str, str], Awaitable[dict]]) -> None: ...
    async def stop(self) -> None: ...

class BaseRabbitMQProducer:
    """Async producer for RPC replies and fire-and-forget publishes."""
    async def reply(self, reply_to: str, correlation_id: str, body: dict) -> None: ...
    async def publish(self, routing_key: str, body: dict, **msg_kwargs) -> None: ...
```

### `gateway/app/core/rpc_client.py` (replaces `kafka_request_client.py`)

```python
class GatewayRPCClient:
    async def request(
        self,
        routing_key: str,
        payload: dict,
        timeout: float = 30.0,
    ) -> dict:
        correlation_id = str(uuid.uuid4())
        reply_queue = await self._channel.declare_queue(exclusive=True, auto_delete=True)

        await self._exchange.publish(
            Message(
                body=json.dumps(envelope).encode(),
                correlation_id=correlation_id,
                reply_to=reply_queue.name,
                content_type="application/json",
            ),
            routing_key=routing_key,
        )

        async with asyncio.timeout(timeout):
            async for message in reply_queue.iterator():
                async with message.process():
                    return json.loads(message.body)
```

### Per-service `messaging/implementations/rabbitmq.py` (new, replaces `kafka.py`)

Each of the 6 RPC services gets a `RabbitMQConsumerImpl` and `RabbitMQProducerImpl` that subclass the shared base classes — same pattern as the existing Kafka implementations, just different transport.

Embedding service keeps its `kafka.py` for the pipeline and adds a `rabbitmq.py` for its own request queue.

### Config changes (all RPC services)

**Remove:**
```
kafka_bootstrap_servers
kafka_max_retries
kafka_retry_delay  
kafka_consumer_timeout_ms
kafka_api_version
{service}_topic / request_topic / response_topic / etc.
```

**Add:**
```
rabbitmq_url            = amqp://guest:guest@rabbitmq:5672/
rabbitmq_exchange       = ragapp.requests
rabbitmq_queue          = {service_name}
rabbitmq_prefetch_count = 1
```

Embedding service retains all `kafka_*` fields plus gains the new `rabbitmq_*` fields.

---

## Infrastructure Changes

### `docker-compose.yml`

Add RabbitMQ service:
```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  ports:
    - "5672:5672"
    - "15672:15672"
  environment:
    RABBITMQ_DEFAULT_USER: guest
    RABBITMQ_DEFAULT_PASS: guest
  healthcheck:
    test: rabbitmq-diagnostics check_port_connectivity
    interval: 10s
    retries: 5
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
```

All RPC services add to `depends_on`:
```yaml
depends_on:
  rabbitmq:
    condition: service_healthy
```

Kafka and Zookeeper remain unchanged.

### `requirements.txt` per service

| Service    | Remove          | Add              |
|------------|-----------------|------------------|
| gateway    | `kafka-python`  | `aio-pika>=9.4`  |
| files      | `kafka-python`  | `aio-pika>=9.4`  |
| memory     | `kafka-python`  | `aio-pika>=9.4`  |
| llm_agent  | `kafka-python`  | `aio-pika>=9.4`  |
| rag        | `kafka-python`  | `aio-pika>=9.4`  |
| vector_db  | `kafka-python`  | `aio-pika>=9.4`  |
| embedding  | —               | `aio-pika>=9.4`  |
| shared     | —               | `aio-pika>=9.4`  |

---

## Error Handling

- **Consumer exception** → `message.nack(requeue=False)` → message goes to DLQ (via RabbitMQ dead-letter-exchange, replacing the custom `shared/dlq.py` for RPC flows)
- **RPC timeout** → `asyncio.TimeoutError` raised at gateway, exclusive reply queue auto-deletes via TTL
- **Connection loss** → `aio_pika.connect_robust()` handles reconnection automatically
- **Service unavailable** → gateway catches `TimeoutError`, returns `503` to client (same as current behaviour)

---

## Testing

- Unit tests for `BaseRabbitMQConsumer` and `BaseRabbitMQProducer` using `aio-pika`'s test utilities or `pytest-asyncio` with a mock channel
- Existing gateway tests updated to mock `GatewayRPCClient.request()` directly (same interface as current `GatewayKafkaRequestClient.request()`)
- Integration: `docker-compose up rabbitmq` + `pytest` with real broker for end-to-end RPC round-trip tests

---

## Files Modified / Created / Deleted

### New
- `shared/rabbitmq_base.py`
- `gateway/app/core/rpc_client.py`
- `{service}/app/messaging/implementations/rabbitmq.py` (×6)

### Modified
- `gateway/app/main.py` — wire RPC client in lifespan
- `gateway/app/core/config.py` — swap kafka fields for rabbitmq fields
- `gateway/app/services/*.py` — inject `GatewayRPCClient` instead of `GatewayKafkaRequestClient`
- `gateway/app/messaging/factories.py` — return RabbitMQ impls
- `{service}/app/main.py` — replace thread consumers with async lifespan consumers (×6)
- `{service}/app/core/config.py` — swap fields (×6)
- `{service}/app/messaging/factories.py` — return RabbitMQ impls (×6)
- `docker-compose.yml` — add RabbitMQ service + volume
- `.env.example` — add `RABBITMQ_URL`, remove per-service Kafka topic vars
- `docker/requirements-base.txt` — add `aio-pika`

### Deleted
- `gateway/app/core/kafka_reply_router.py`
- `gateway/app/core/request_matcher.py`
- `gateway/app/core/kafka_client.py`
- `gateway/app/core/kafka_request_client.py`
- `{service}/app/messaging/implementations/kafka.py` (×6, not embedding)

---

## What Does NOT Change

- `shared/kafka_base.py` — kept, embedding pipeline uses it
- `embedding/app/messaging/embedding_kafka.py` — kept
- `embedding/app/services/embedding_job_publisher.py` — kept
- `embedding/app/consumers.py` `process_embedding_job_requests` — kept
- `vector_db` Kafka consumer for upsert pipeline — kept
- All business logic in service handlers — zero changes
- All Pydantic envelope schemas — zero changes
- Frontend — zero changes
