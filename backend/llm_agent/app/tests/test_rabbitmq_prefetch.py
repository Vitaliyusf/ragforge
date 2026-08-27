"""Deterministic tests for llm_agent RabbitMQ prefetch selection."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.messaging.implementations.rabbitmq import make_consumer


def _settings(**overrides: object) -> Settings:
    values = {
        "default_model": "test-model",
        "rag_chat_model": "test-model",
        **overrides,
    }
    return Settings(**values)


def test_llm_request_prefetch_defaults_to_four() -> None:
    assert _settings().llm_request_prefetch == 4


def test_primary_llm_queue_uses_dedicated_prefetch() -> None:
    settings = _settings(llm_request_prefetch=4, rabbitmq_prefetch_count=1)

    consumer = make_consumer(settings, settings.rabbitmq_queue)

    assert consumer.config.rabbitmq_prefetch_count == 4


@pytest.mark.parametrize(
    "queue_field",
    [
        "summary_queue",
        "metadata_queue",
        "generate_questions_queue",
        "model_queue",
        "model_management_queue",
        "config_management_queue",
    ],
)
def test_unrelated_queues_retain_global_prefetch(queue_field: str) -> None:
    settings = _settings(llm_request_prefetch=4, rabbitmq_prefetch_count=2)

    consumer = make_consumer(settings, getattr(settings, queue_field))

    assert consumer.config.rabbitmq_prefetch_count == 2


@pytest.mark.parametrize("invalid_prefetch", [-1, 0, 5])
def test_llm_request_prefetch_rejects_out_of_bounds_values(
    invalid_prefetch: int,
) -> None:
    with pytest.raises(ValidationError):
        _settings(llm_request_prefetch=invalid_prefetch)


@pytest.mark.asyncio
async def test_consumer_applies_dedicated_qos_and_can_restart_cleanly() -> None:
    settings = _settings(llm_request_prefetch=2)
    consumer = make_consumer(settings, settings.rabbitmq_queue)
    handler = AsyncMock(return_value=None)

    connections = []
    for _ in range(2):
        queue = AsyncMock()
        channel = AsyncMock()
        channel.declare_exchange.return_value = AsyncMock()
        channel.declare_queue.return_value = queue
        connection = AsyncMock()
        connection.is_closed = False
        connection.channel.return_value = channel
        connections.append((connection, channel, queue))

    with patch(
        "shared.rabbitmq_base.aio_pika.connect_robust",
        new=AsyncMock(side_effect=[item[0] for item in connections]),
    ):
        for connection, channel, queue in connections:
            await consumer.start(handler)
            channel.set_qos.assert_awaited_once_with(prefetch_count=2)
            queue.consume.assert_awaited_once()

            await consumer.stop()
            connection.close.assert_awaited_once()
