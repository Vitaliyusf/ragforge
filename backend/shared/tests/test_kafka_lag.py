"""Tests for the Kafka consumer-lag gauge and the consume-path wiring.

Two halves, deliberately split across two modules:

- The offset arithmetic and the gauge write live in ``shared.metrics``, which
  has no Kafka dependency, so those tests import it directly.
- The wiring lives in ``shared.kafka_base``, which imports kafka-python. That
  driver is in neither ``docker/requirements-base.txt`` nor
  ``backend/requirements-dev.txt``, so it is absent wherever these tests run;
  the ``kafka_base`` fixture stubs it rather than skipping, so the wiring is
  actually exercised in CI instead of being permanently skipped.
"""
from __future__ import annotations

import collections
import importlib
import sys
import types
from typing import Any, Iterator, List, cast

import pytest

from shared.metrics import METRICS, observe_kafka_consumer_lag

prometheus = pytest.importorskip("prometheus_client")

Record = collections.namedtuple("Record", ["topic", "partition", "offset", "value"])


def gauge_value(*, service: str, topic: str, group: str) -> float:
    """Current value of the lag gauge for one label set."""
    return cast(float, METRICS.kafka_consumer_lag.labels(
        service=service, topic=topic, group=group
    )._value.get())


def has_series(*, service: str, topic: str, group: str) -> bool:
    """Whether any sample has been written for one label set.

    Reading the child registry rather than the value, because the distinction
    under test is "no series at all" versus "a series reading zero".
    """
    return (service, topic, group) in METRICS.kafka_consumer_lag._metrics


# ── Offset arithmetic ─────────────────────────────────────────────────────

def test_lag_is_the_distance_between_the_two_next_offsets() -> None:
    """Both values are *next* offsets, so the subtraction needs no correction."""
    lag = observe_kafka_consumer_lag(
        "files", "lag-basic", "g", highwater=110, next_offset=100
    )

    assert lag == 10
    assert gauge_value(service="files", topic="lag-basic", group="g") == 10


def test_a_caught_up_consumer_records_a_genuine_zero() -> None:
    """0 here is a measurement, unlike the 0 an unknown offset must not write."""
    lag = observe_kafka_consumer_lag(
        "files", "lag-caught-up", "g", highwater=100, next_offset=100
    )

    assert lag == 0
    assert has_series(service="files", topic="lag-caught-up", group="g")
    assert gauge_value(service="files", topic="lag-caught-up", group="g") == 0


@pytest.mark.parametrize(
    "highwater,next_offset",
    [(None, 100), (110, None), (None, None)],
    ids=["no-highwater", "no-position", "neither"],
)
def test_an_unknown_offset_records_nothing(highwater: Any, next_offset: Any) -> None:
    """Not merely "returns None" — no series may be created at all.

    A gauge reading 0 because the offset was unavailable is indistinguishable
    from a consumer that is keeping up, which is the reading an operator would
    trust and act on.
    """
    topic = f"lag-unknown-{highwater}-{next_offset}"

    lag = observe_kafka_consumer_lag(
        "files", topic, "g", highwater=highwater, next_offset=next_offset
    )

    assert lag is None
    assert not has_series(service="files", topic=topic, group="g")


def test_a_negative_difference_is_clamped_to_zero() -> None:
    """A cached highwater can trail the position; lag is never below zero."""
    lag = observe_kafka_consumer_lag(
        "files", "lag-negative", "g", highwater=100, next_offset=105
    )

    assert lag == 0


def test_each_topic_and_group_is_its_own_series() -> None:
    """Lag is per topic and group; one must not overwrite another."""
    observe_kafka_consumer_lag("files", "lag-a", "group-1", highwater=10, next_offset=0)
    observe_kafka_consumer_lag("files", "lag-a", "group-2", highwater=30, next_offset=0)

    assert gauge_value(service="files", topic="lag-a", group="group-1") == 10
    assert gauge_value(service="files", topic="lag-a", group="group-2") == 30


# ── Consume-path wiring ───────────────────────────────────────────────────

@pytest.fixture
def kafka_base(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import ``shared.kafka_base`` against a stubbed kafka driver.

    kafka-python is in no shared requirements file, so the real driver is not
    installed where these tests run, and `importorskip` would make this a test
    that never executes in CI either. Stubbing the two names kafka_base imports
    lets the lag wiring be tested for real: what is under test is the offset
    arithmetic and the gauge write, neither of which touches the driver.
    """
    kafka = types.ModuleType("kafka")
    kafka.KafkaConsumer = object  # type: ignore[attr-defined]
    kafka.KafkaProducer = object  # type: ignore[attr-defined]
    structs = types.ModuleType("kafka.structs")
    structs.TopicPartition = collections.namedtuple(  # type: ignore[attr-defined,misc]
        "TopicPartition", ["topic", "partition"]
    )
    kafka.structs = structs  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "kafka", kafka)
    monkeypatch.setitem(sys.modules, "kafka.structs", structs)
    monkeypatch.delitem(sys.modules, "shared.kafka_base", raising=False)
    module = importlib.import_module("shared.kafka_base")
    yield module
    # Never leave the stub-built module cached for another test to import.
    sys.modules.pop("shared.kafka_base", None)


class FakeConsumer:
    """A consumer exposing known offsets, as kafka-python's does after a fetch."""

    def __init__(self, records: List[Record], highwater: Any) -> None:
        self._records = records
        self._highwater = highwater

    def __iter__(self) -> Iterator[Record]:
        return iter(self._records)

    def highwater(self, partition: Any) -> Any:
        if isinstance(self._highwater, Exception):
            raise self._highwater
        return self._highwater


class FakeConfig:
    """The Kafka fields ``_KafkaConfigProtocol`` requires."""

    service_name = "files"
    kafka_bootstrap_servers = "kafka:9092"
    kafka_max_retries = 1
    kafka_retry_delay = 0
    kafka_consumer_timeout_ms = 1
    kafka_api_version = (2, 0, 2)


def build_consumer(
    kafka_base: Any, topic: str, group: str, *, records: List[Record], highwater: Any
) -> Any:
    """A BaseKafkaConsumer with its client already replaced by a double."""
    consumer = kafka_base.BaseKafkaConsumer(FakeConfig(), topic, group)
    consumer._consumer = FakeConsumer(records, highwater)
    return consumer


def message(topic: str, offset: int) -> Record:
    return Record(topic=topic, partition=0, offset=offset, value={"payload": offset})


def test_consuming_a_message_records_the_lag(kafka_base: Any) -> None:
    """The gauge is updated on the path that was already running."""
    consumer = build_consumer(
        kafka_base, "wire-basic", "grp", records=[message("wire-basic", 41)], highwater=50
    )

    assert list(consumer.consume()) == [{"payload": 41}]
    # 50 - 42: both are *next* offsets, and the record just yielded is consumed.
    assert gauge_value(service="files", topic="wire-basic", group="grp") == 8


def test_the_last_message_of_a_caught_up_partition_reads_zero(kafka_base: Any) -> None:
    consumer = build_consumer(
        kafka_base, "wire-caught-up", "grp", records=[message("wire-caught-up", 9)], highwater=10
    )

    list(consumer.consume())

    assert gauge_value(service="files", topic="wire-caught-up", group="grp") == 0


def test_an_unknown_highwater_writes_no_series_and_still_consumes(kafka_base: Any) -> None:
    """Before the first FetchResponse there is no highwater to compare against."""
    consumer = build_consumer(
        kafka_base, "wire-unknown", "grp", records=[message("wire-unknown", 5)], highwater=None
    )

    assert list(consumer.consume()) == [{"payload": 5}]
    assert not has_series(service="files", topic="wire-unknown", group="grp")


def test_a_failing_gauge_never_breaks_consumption(kafka_base: Any) -> None:
    """Lag is a monitoring side-effect of consuming; it must not stop it.

    This is what makes the broad `except` in `_record_lag` a deliberate choice:
    a service must keep processing its messages when metrics misbehave.
    """
    consumer = build_consumer(
        kafka_base,
        "wire-broken",
        "grp",
        records=[message("wire-broken", 1), message("wire-broken", 2)],
        highwater=RuntimeError("offsets unavailable"),
    )

    assert list(consumer.consume()) == [{"payload": 1}, {"payload": 2}]
    assert not has_series(service="files", topic="wire-broken", group="grp")


def test_the_config_service_name_labels_the_series(kafka_base: Any) -> None:
    """The gauge is labelled with the recording service, from its config."""
    consumer = build_consumer(
        kafka_base, "wire-labelled", "grp", records=[message("wire-labelled", 0)], highwater=4
    )

    list(consumer.consume())

    assert gauge_value(service="files", topic="wire-labelled", group="grp") == 3


def test_a_config_without_a_service_name_mislabels_rather_than_crashing(kafka_base: Any) -> None:
    """`_record_lag` reads service_name defensively, and this proves why.

    `_KafkaConfigProtocol` documents the field but enforces nothing — it is
    duck-typed, not a base class. A config missing it should cost a correct
    label, never a consumer that stops processing messages.
    """

    class NamelessConfig:
        kafka_bootstrap_servers = "kafka:9092"
        kafka_max_retries = 1
        kafka_retry_delay = 0
        kafka_consumer_timeout_ms = 1
        kafka_api_version = (2, 0, 2)

    consumer = kafka_base.BaseKafkaConsumer(NamelessConfig(), "wire-nameless", "grp")
    consumer._consumer = FakeConsumer([message("wire-nameless", 0)], highwater=4)

    assert list(consumer.consume()) == [{"payload": 0}]
    assert gauge_value(service="unknown", topic="wire-nameless", group="grp") == 3


def test_lag_uses_the_message_topic_not_the_subscription(kafka_base: Any) -> None:
    """A consumer subscribed to one topic still labels by the record's topic."""
    consumer = build_consumer(
        kafka_base,
        "wire-subscribed",
        "grp",
        records=[message("wire-actual", 0)],
        highwater=7,
    )

    list(consumer.consume())

    assert gauge_value(service="files", topic="wire-actual", group="grp") == 6
    assert not has_series(service="files", topic="wire-subscribed", group="grp")
