"""Transport readiness must track broker loss and recovery, not object creation."""
from shared.kafka_base import BaseKafkaConsumer, BaseKafkaProducer


class KafkaState:
    def __init__(self, connected: bool) -> None:
        self.connected = connected

    def bootstrap_connected(self) -> bool:
        return self.connected


def test_kafka_producer_readiness_tracks_recovery() -> None:
    producer = object.__new__(BaseKafkaProducer)
    producer._producer = KafkaState(True)
    assert producer.is_connected() is True
    producer._producer.connected = False
    assert producer.is_connected() is False
    producer._producer.connected = True
    assert producer.is_connected() is True


def test_kafka_consumer_uninitialized_failure_and_recovery() -> None:
    consumer = object.__new__(BaseKafkaConsumer)
    consumer._consumer = None
    assert consumer.is_connected() is False
    consumer._consumer = KafkaState(False)
    assert consumer.is_connected() is False
    consumer._consumer.connected = True
    assert consumer.is_connected() is True
