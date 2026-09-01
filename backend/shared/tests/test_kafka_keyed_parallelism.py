"""Focused correctness tests for bounded partition-parallel Kafka workers."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable

import pytest

from shared.kafka_base import BaseKafkaProducer, kafka_document_key
from shared.kafka_workers import KafkaConsumerWorkerPool


def test_document_key_prefers_document_id_and_supports_legacy_file_id() -> None:
    assert kafka_document_key(
        {"payload": {"document_id": "doc-1", "file_id": "file-1"}}
    ) == "doc-1"
    assert kafka_document_key({"payload": {"file_id": "file-1"}}) == "file-1"
    assert kafka_document_key(
        {"payload": {"chunks": [{"document_id": "doc-1", "file_id": "file-1"}]}}
    ) == "doc-1"
    assert kafka_document_key({"file_id": "legacy-file"}) == "legacy-file"
    assert kafka_document_key({"payload": {}}) is None


def test_producer_forwards_optional_key_without_breaking_unkeyed_topics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Config:
        kafka_bootstrap_servers = "unused"
        service_name = "test"
        kafka_max_retries = 1
        kafka_retry_delay = 0
        kafka_consumer_timeout_ms = 1
        kafka_api_version = (0, 10, 1)

    class RawProducer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict, str | None]] = []

        def send(self, topic: str, message: dict, *, key: str | None) -> None:
            self.calls.append((topic, message, key))

    monkeypatch.setattr("shared.kafka_base.attach_internal_auth_context", lambda message: message)
    producer = BaseKafkaProducer(Config())
    raw = RawProducer()
    producer._producer = raw

    producer.send("pipeline", {"payload": {"document_id": "doc-1"}}, key="doc-1")
    producer.send("unkeyed", {"value": 1})

    assert [call[2] for call in raw.calls] == ["doc-1", None]


def test_partition_workers_overlap_keys_preserve_key_order_and_bound_concurrency() -> None:
    records = [
        [(0, "doc-a"), (2, "doc-a")],
        [(1, "doc-b"), (3, "doc-b")],
        [(4, "doc-c")],
    ]
    lock = threading.Lock()
    active = 0
    maximum = 0
    completed: dict[str, list[int]] = defaultdict(list)

    class Consumer:
        def __init__(self, assigned: list[tuple[int, str]]) -> None:
            self.assigned = assigned
            self.closed = False

        def close(self) -> None:
            self.closed = True

    consumers = iter(Consumer(assigned) for assigned in records)

    def target(consumer: Consumer) -> Callable[[], None]:
        def run() -> None:
            nonlocal active, maximum
            for sequence, key in consumer.assigned:
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.02)
                with lock:
                    completed[key].append(sequence)
                    active -= 1

        return run

    pool = KafkaConsumerWorkerPool(
        worker_count=3,
        consumer_factory=lambda: next(consumers),
        target_factory=target,
        thread_name_prefix="keyed-test",
    ).start()

    assert pool.close(timeout=1.0) is True
    assert completed == {"doc-a": [0, 2], "doc-b": [1, 3], "doc-c": [4]}
    assert maximum == 3
    assert len(pool.threads) == 3
    assert all(not thread.is_alive() for thread in pool.threads)


def test_one_partition_failure_does_not_reorder_another_partition() -> None:
    records = [
        [(0, "failed"), (2, "failed")],
        [(1, "healthy"), (3, "healthy")],
    ]
    completed: dict[str, list[int]] = defaultdict(list)

    class Consumer:
        def __init__(self, assigned: list[tuple[int, str]]) -> None:
            self.assigned = assigned

        def close(self) -> None:
            return None

    consumers = iter(Consumer(assigned) for assigned in records)

    def target(consumer: Consumer) -> Callable[[], None]:
        def run() -> None:
            for sequence, key in consumer.assigned:
                if key == "failed" and sequence == 0:
                    break
                completed[key].append(sequence)

        return run

    pool = KafkaConsumerWorkerPool(
        worker_count=2,
        consumer_factory=lambda: next(consumers),
        target_factory=target,
        thread_name_prefix="failure-test",
    ).start()

    assert pool.close(timeout=1.0) is True
    assert completed["failed"] == []
    assert completed["healthy"] == [1, 3]


def test_close_unblocks_all_consumers_without_leaking_threads() -> None:
    started = threading.Barrier(3)

    class Consumer:
        def __init__(self) -> None:
            self.released = threading.Event()

        def close(self) -> None:
            self.released.set()

    def target(consumer: Consumer) -> Callable[[], None]:
        def run() -> None:
            started.wait(timeout=1.0)
            consumer.released.wait(timeout=1.0)

        return run

    pool = KafkaConsumerWorkerPool(
        worker_count=2,
        consumer_factory=Consumer,
        target_factory=target,
        thread_name_prefix="shutdown-test",
    ).start()
    started.wait(timeout=1.0)

    assert pool.close(timeout=1.0) is True
    assert all(not thread.is_alive() for thread in pool.threads)


def test_worker_pool_readiness_tracks_all_consumers_and_threads() -> None:
    release = threading.Event()

    class Consumer:
        def __init__(self) -> None:
            self.connected = True

        def is_connected(self) -> bool:
            return self.connected

        def close(self) -> None:
            self.connected = False
            release.set()

    def target(_consumer: Consumer) -> Callable[[], None]:
        return lambda: release.wait(timeout=1.0)

    pool = KafkaConsumerWorkerPool(
        worker_count=2,
        consumer_factory=Consumer,
        target_factory=target,
        thread_name_prefix="readiness-test",
    )

    assert pool.is_connected() is False
    pool.start()
    assert pool.is_connected() is True
    pool.consumers[0].connected = False
    assert pool.is_connected() is False
    assert pool.close(timeout=1.0) is True
    assert pool.is_connected() is False
