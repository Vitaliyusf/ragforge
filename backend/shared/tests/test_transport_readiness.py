"""Transport readiness must track broker loss and recovery, not object creation."""
from typing import List, Sequence

from shared.kafka_base import BaseKafkaConsumer, BaseKafkaProducer


class KafkaState:
    def __init__(self, connected: bool) -> None:
        self.connected = connected

    def bootstrap_connected(self) -> bool:
        return self.connected


class _Broker:
    def __init__(self, node_id: int) -> None:
        self.nodeId = node_id


class _Cluster:
    def __init__(self, node_ids: Sequence[int]) -> None:
        self._node_ids = node_ids

    def brokers(self) -> List[_Broker]:
        return [_Broker(n) for n in self._node_ids]


class _Client:
    """A kafka-python client that has moved past its bootstrap connection."""

    def __init__(
        self, connected_nodes: Sequence[int], all_nodes: Sequence[int] = (1,)
    ) -> None:
        self._connected = set(connected_nodes)
        self.cluster = _Cluster(all_nodes)

    def connected(self, node_id: int) -> bool:
        return node_id in self._connected


class PostBootstrapConsumer(KafkaState):
    """kafka-python >= 2.2 drops the bootstrap connection once metadata lands."""

    def __init__(self, connected_nodes: Sequence[int]) -> None:
        super().__init__(False)
        self._client = _Client(connected_nodes)


class PostBootstrapProducer(KafkaState):
    def __init__(self, connected_nodes: Sequence[int]) -> None:
        super().__init__(False)
        self._sender = type("_Sender", (), {"_client": _Client(connected_nodes)})()


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


def test_kafka_consumer_is_ready_once_the_bootstrap_connection_is_gone() -> None:
    """A consumer talking to a broker is ready even with bootstrap closed."""
    consumer = object.__new__(BaseKafkaConsumer)
    consumer._consumer = PostBootstrapConsumer(connected_nodes=[1])
    assert consumer.is_connected() is True

    consumer._consumer = PostBootstrapConsumer(connected_nodes=[])
    assert consumer.is_connected() is False


def test_kafka_producer_is_ready_once_the_bootstrap_connection_is_gone() -> None:
    producer = object.__new__(BaseKafkaProducer)
    producer._producer = PostBootstrapProducer(connected_nodes=[1])
    assert producer.is_connected() is True

    producer._producer = PostBootstrapProducer(connected_nodes=[])
    assert producer.is_connected() is False
