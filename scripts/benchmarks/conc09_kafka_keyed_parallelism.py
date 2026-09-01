"""Controlled CONC-09 keyed-consumer throughput benchmark.

This is intentionally broker-free: it measures the processing shape changed by
CONC-09 without including Kafka/container startup.  Each worker represents one
Kafka partition consumer, and a stable key-to-partition mapping keeps a key's
messages on one serial worker.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable


def _partition(key: str, workers: int) -> int:
    return zlib.crc32(key.encode("utf-8")) % workers


def _run(keys: Iterable[str], workers: int, processing_seconds: float) -> dict[str, float | int]:
    queues: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for sequence, key in enumerate(keys):
        queues[_partition(key, workers)].append((sequence, key))

    active = 0
    maximum = 0
    errors = 0
    violations = 0
    last_sequence: dict[str, int] = {}
    durations: list[float] = []
    lock = threading.Lock()

    def process_partition(records: list[tuple[int, str]]) -> None:
        nonlocal active, maximum, errors, violations
        for sequence, key in records:
            item_started = time.perf_counter()
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(processing_seconds)
                with lock:
                    previous = last_sequence.get(key)
                    if previous is not None and sequence <= previous:
                        violations += 1
                    last_sequence[key] = sequence
            except Exception:
                with lock:
                    errors += 1
            finally:
                with lock:
                    active -= 1
                    durations.append((time.perf_counter() - item_started) * 1000)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_partition, records) for records in queues.values()]
        for future in futures:
            future.result()
    wall = time.perf_counter() - started
    ordered_durations = sorted(durations)
    p95_index = int(0.95 * (len(ordered_durations) - 1))
    message_count = len(ordered_durations)
    return {
        "messages": message_count,
        "wall_s": round(wall, 4),
        "throughput_msg_s": round(message_count / wall, 2),
        "p50_ms": round(statistics.median(ordered_durations), 2),
        "p95_ms": round(ordered_durations[p95_index], 2),
        "max_concurrency": maximum,
        "ordering_violations": violations,
        "errors": errors,
        "backlog_peak": message_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--processing-ms", type=float, default=15.0)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    workloads = {
        "many_keys": [f"doc-{index % 12}" for index in range(48)],
        "hot_key": ["hot" if index < 36 else f"doc-{index}" for index in range(48)],
    }
    results = {
        name: _run(keys, args.workers, args.processing_ms / 1000)
        for name, keys in workloads.items()
    }
    print(json.dumps({"workers": args.workers, "workloads": results}, indent=2))


if __name__ == "__main__":
    main()
