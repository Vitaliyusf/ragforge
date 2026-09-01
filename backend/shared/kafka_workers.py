"""Bounded lifecycle management for partition-parallel Kafka consumers."""
from __future__ import annotations

import time
from collections.abc import Callable
from threading import Thread
from typing import Any


class KafkaConsumerWorkerPool:
    """Own a fixed number of consumers and their single-threaded workers.

    Kafka assigns partitions across consumers in the same group. Each worker
    stays serial, so a keyed partition never has in-process out-of-order offset
    completion while independent partitions can make progress concurrently.
    """

    def __init__(
        self,
        *,
        worker_count: int,
        consumer_factory: Callable[[], Any],
        target_factory: Callable[[Any], Callable[[], None]],
        thread_name_prefix: str,
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        self._worker_count = worker_count
        self._consumer_factory = consumer_factory
        self._target_factory = target_factory
        self._thread_name_prefix = thread_name_prefix
        self.consumers: list[Any] = []
        self.threads: list[Thread] = []

    def start(self) -> "KafkaConsumerWorkerPool":
        """Create and start exactly the configured number of workers."""
        if self.threads:
            raise RuntimeError("Kafka consumer worker pool already started")
        try:
            for index in range(self._worker_count):
                consumer = self._consumer_factory()
                thread = Thread(
                    target=self._target_factory(consumer),
                    daemon=True,
                    name=f"{self._thread_name_prefix}-{index + 1}",
                )
                self.consumers.append(consumer)
                self.threads.append(thread)
            for thread in self.threads:
                thread.start()
        except Exception:
            self.close(timeout=0)
            raise
        return self

    def close(self, *, timeout: float = 10.0) -> bool:
        """Close consumers, join workers to one shared deadline, and report drain."""
        for consumer in self.consumers:
            try:
                consumer.close()
            except Exception:
                pass
        deadline = time.monotonic() + max(0.0, timeout)
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self.threads)
