"""Small live-Qdrant operation benchmark owned by VECTOR-02.

Run inside the vector_db container so it uses the pinned client and the same
Qdrant server/network as the service. The script owns and always removes a
uniquely named temporary collection.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import resource
from statistics import median
import time
import tracemalloc
import uuid

from qdrant_client import QdrantClient, models


VECTOR_SIZE = 32
SEARCH_RUNS = 30
DELETE_RUNS = 3
DELETE_SIZES = {"small": 10, "medium": 1_000, "large": 5_000}


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def summary(samples: list[float]) -> dict[str, float]:
    return {
        "p50_ms": round(median(samples) * 1_000, 3),
        "p95_ms": round(percentile(samples, 0.95) * 1_000, 3),
    }


def timed(function):
    started = time.perf_counter()
    value = function()
    return time.perf_counter() - started, value


def client_rrf(dense, sparse, k: int = 60):
    fused = {}
    for arm, candidates in (("dense", dense), ("sparse", sparse)):
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = candidate.payload["chunk_id"]
            entry = fused.setdefault(
                chunk_id,
                {"score": 0.0, "dense_rank": None, "sparse_rank": None},
            )
            rank_key = f"{arm}_rank"
            if entry[rank_key] is None:
                entry[rank_key] = rank
                entry["score"] += 1.0 / (k + rank)
    return sorted(
        fused.items(),
        key=lambda item: (
            -item[1]["score"],
            min(
                rank
                for rank in (item[1]["dense_rank"], item[1]["sparse_rank"])
                if rank is not None
            ),
            item[0],
        ),
    )


def filter_for(file_id: str | None = None) -> models.Filter:
    must = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value="vector02")),
        models.FieldCondition(
            key="retrieval_allowed", match=models.MatchValue(value=True)
        ),
    ]
    if file_id:
        must.append(models.FieldCondition(key="file_id", match=models.MatchValue(value=file_id)))
    return models.Filter(
        must=must,
        must_not=[
            models.FieldCondition(
                key="review_status", match=models.MatchValue(value="removed")
            )
        ],
    )


def points(count: int, file_id: str, start_id: int) -> list[models.PointStruct]:
    dense = [1.0 / math.sqrt(VECTOR_SIZE)] * VECTOR_SIZE
    return [
        models.PointStruct(
            id=start_id + index,
            vector={
                "dense": dense,
                "lexical": models.SparseVector(indices=[1, 2], values=[1.0, 0.5]),
            },
            payload={
                "tenant_id": "vector02",
                "owner_admin_id": "vector02-admin",
                "file_id": file_id,
                "document_id": file_id,
                "chunk_id": f"{file_id}-{index}",
                "retrieval_allowed": True,
                "review_status": "clean",
            },
        )
        for index in range(count)
    ]


def upsert_batches(client, collection: str, batch: list[models.PointStruct]) -> int:
    calls = 0
    for offset in range(0, len(batch), 256):
        client.upsert(
            collection_name=collection,
            points=batch[offset : offset + 256],
            wait=True,
        )
        calls += 1
    return calls


def main() -> None:
    collection = f"vector02_bench_{uuid.uuid4().hex[:12]}"
    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "qdrant"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY") or None,
        https=False,
    )
    cpu_started = time.process_time()
    rss_started = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    output: dict[str, object] = {
        "kind": "live pinned-runtime benchmark",
        "server_expected": "qdrant/qdrant:v1.18.2-unprivileged",
        "client_version": "1.19.0",
    }
    try:
        client.create_collection(
            collection_name=collection,
            vectors_config={
                "dense": models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={"lexical": models.SparseVectorParams()},
        )
        for field in (
            "tenant_id",
            "owner_admin_id",
            "file_id",
            "document_id",
            "chunk_id",
            "retrieval_allowed",
            "review_status",
        ):
            schema = models.PayloadSchemaType.BOOL if field == "retrieval_allowed" else models.PayloadSchemaType.KEYWORD
            client.create_payload_index(collection, field, schema, wait=True)

        seed = points(512, "search", 1)
        elapsed, upsert_calls = timed(lambda: upsert_batches(client, collection, seed))
        output["upsert"] = {
            "points": len(seed),
            "calls": upsert_calls,
            "throughput_points_per_second": round(len(seed) / elapsed, 1),
        }

        dense_query = [1.0 / math.sqrt(VECTOR_SIZE)] * VECTOR_SIZE
        query_filter = filter_for()

        def dense():
            return client.query_points(
                collection,
                query=dense_query,
                using="dense",
                query_filter=query_filter,
                limit=20,
                with_payload=True,
            ).points

        def sparse():
            return client.query_points(
                collection,
                query=models.SparseVector(indices=[1], values=[1.0]),
                using="lexical",
                query_filter=query_filter,
                limit=20,
                with_payload=True,
            ).points

        dense_times = [timed(dense)[0] for _ in range(SEARCH_RUNS)]
        sparse_times = [timed(sparse)[0] for _ in range(SEARCH_RUNS)]
        serial_times = []
        concurrent_times = []
        equivalent = True
        serial_results = (dense(), sparse())
        for _ in range(SEARCH_RUNS):
            elapsed, serial_results = timed(lambda: (dense(), sparse()))
            serial_times.append(elapsed)
        with ThreadPoolExecutor(max_workers=2) as executor:
            for _ in range(SEARCH_RUNS):
                started = time.perf_counter()
                dense_future = executor.submit(dense)
                sparse_future = executor.submit(sparse)
                concurrent_results = (dense_future.result(), sparse_future.result())
                concurrent_times.append(time.perf_counter() - started)
                equivalent &= client_rrf(*serial_results) == client_rrf(*concurrent_results)

        output["search"] = {
            "dense": {"before": summary(dense_times), "after": summary(dense_times), "calls": 1},
            "sparse": {"before": summary(sparse_times), "after": summary(sparse_times), "calls": 1},
            "hybrid": {
                "before": summary(serial_times),
                "after": summary(concurrent_times),
                "calls_before": 2,
                "calls_after": 2,
                "client_rrf_equivalent": equivalent,
            },
        }
        output["server_side_fusion"] = {
            "supported_by_pins": True,
            "selected": False,
            "reason": "one fused response omits required per-arm ranks/scores and cannot enforce the chunk-id tie-break contract",
        }

        delete_output = {}
        next_id = 100_000
        for label, match_count in DELETE_SIZES.items():
            before_times = []
            after_times = []
            before_peaks = []
            after_peaks = []
            before_calls = []
            for run in range(DELETE_RUNS):
                baseline_file = f"baseline-{label}-{run}"
                after_file = f"after-{label}-{run}"
                baseline_points = points(match_count, baseline_file, next_id)
                next_id += match_count
                after_points = points(match_count, after_file, next_id)
                next_id += match_count
                upsert_batches(client, collection, baseline_points)
                upsert_batches(client, collection, after_points)

                tracemalloc.start()
                started = time.perf_counter()
                ids = []
                offset = None
                calls = 0
                baseline_filter = filter_for(baseline_file)
                while True:
                    records, offset = client.scroll(
                        collection,
                        scroll_filter=baseline_filter,
                        offset=offset,
                        limit=256,
                        with_payload=False,
                        with_vectors=False,
                    )
                    calls += 1
                    ids.extend(record.id for record in records)
                    if offset is None:
                        break
                client.delete(collection, points_selector=ids, wait=True)
                calls += 1
                before_times.append(time.perf_counter() - started)
                before_peaks.append(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                before_calls.append(calls)

                after_filter = filter_for(after_file)
                tracemalloc.start()
                started = time.perf_counter()
                count = client.count(collection, count_filter=after_filter, exact=True).count
                client.delete(
                    collection,
                    points_selector=models.FilterSelector(filter=after_filter),
                    wait=True,
                )
                after_times.append(time.perf_counter() - started)
                after_peaks.append(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                assert count == match_count

            delete_output[label] = {
                "matches": match_count,
                "before": summary(before_times),
                "after": summary(after_times),
                "calls_before_median": median(before_calls),
                "calls_after": 2,
                "before_peak_python_bytes": max(before_peaks),
                "after_peak_python_bytes": max(after_peaks),
                "ids_materialized_before": match_count,
                "ids_materialized_after": 0,
            }
        output["delete"] = delete_output

        lookup_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id", match=models.MatchValue(value="vector02")
                ),
                models.FieldCondition(
                    key="chunk_id",
                    match=models.MatchAny(any=[f"search-{index}" for index in range(20)]),
                ),
            ]
        )
        lookup_times = []
        for _ in range(SEARCH_RUNS):
            elapsed, _ = timed(
                lambda: client.scroll(
                    collection,
                    scroll_filter=lookup_filter,
                    limit=256,
                    with_payload=["chunk_id", "retrieval_allowed", "review_status"],
                    with_vectors=False,
                )
            )
            lookup_times.append(elapsed)
        output["label_lookup"] = {**summary(lookup_times), "calls": 1}
        output["resources"] = {
            "process_cpu_seconds": round(time.process_time() - cpu_started, 3),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "max_rss_increase_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            - rss_started,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()


if __name__ == "__main__":
    main()
