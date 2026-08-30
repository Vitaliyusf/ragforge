"""A small, deterministic retrieval check over a labelled memory corpus.

This is the measurement hook for the memory architecture, not the memory
benchmark. It runs against a bag-of-words embedding stub, so the numbers prove
that the semantic path is wired correctly end to end — query embedded, index
searched under tenant/user filters, correct memory ranked first — and say
nothing about how the production e5 model would score.
"""

import time

from shared.context import bound_context

from app.tests._memory_harness import (
    BagOfWordsEmbeddingClient,
    InMemoryVectorIndex,
    build_memory_service,
)


TENANT_A = dict(tenant_id="tenant-a", user_id="user-1", role="user")
TENANT_B = dict(tenant_id="tenant-b", user_id="user-9", role="user")
TENANT_A_USER_2 = dict(tenant_id="tenant-a", user_id="user-2", role="user")

# (memory text, query that should retrieve it first)
LABELLED_CORPUS = [
    ("The user migrated the billing database to Postgres in March.", "billing database migration postgres"),
    ("The user shipped the mobile onboarding redesign to production.", "mobile onboarding redesign shipped"),
    ("The user hired two backend engineers for the payments team.", "hired backend engineers payments"),
    ("The user cancelled the Kubernetes cluster upgrade after an outage.", "kubernetes cluster upgrade cancelled"),
    ("The user presented quarterly revenue results to the board.", "quarterly revenue board presentation"),
    ("The user adopted OpenTelemetry tracing across every service.", "opentelemetry tracing adoption"),
    ("The user deprecated the legacy SOAP integration with the vendor.", "legacy soap vendor integration deprecated"),
    ("The user scheduled the annual security penetration test.", "annual security penetration test"),
]


def _candidate(text):
    return {
        "content": {"text": text},
        "event_at": "2026-03-01T00:00:00+00:00",
        "importance": 0.8,
        "confidence": 0.8,
        "provenance": {"explicit_user_signal": True},
    }


def _build():
    return build_memory_service(
        index_client=InMemoryVectorIndex(),
        embedding_client=BagOfWordsEmbeddingClient(),
    )


def _seed(service, identity, corpus, prefix):
    with bound_context(**identity):
        for index, (text, _) in enumerate(corpus):
            service.write_memory(_candidate(text), {"owner_type": "user", "request_id": f"{prefix}-{index}"})


def test_labelled_corpus_is_retrieved_semantically_at_rank_one():
    service, _, _ = _build()
    _seed(service, TENANT_A, LABELLED_CORPUS, "quality-a")

    hits_at_1 = 0
    recall_at_3 = 0
    latencies = []
    with bound_context(**TENANT_A):
        for text, query in LABELLED_CORPUS:
            started = time.perf_counter()
            result = service.get_relevant_memories({"text": query, "limit": 3})
            latencies.append(time.perf_counter() - started)
            returned = [memory["content"]["text"] for memory in result["memories"]]
            assert result["retrieval_mode"] == "semantic"
            if returned and returned[0] == text:
                hits_at_1 += 1
            if text in returned[:3]:
                recall_at_3 += 1

    assert hits_at_1 == len(LABELLED_CORPUS)
    assert recall_at_3 == len(LABELLED_CORPUS)
    assert max(latencies) < 1.0


def test_the_labelled_corpus_leaks_across_no_tenant_or_user_boundary():
    service, _, _ = _build()
    _seed(service, TENANT_A, LABELLED_CORPUS, "quality-a")
    _seed(service, TENANT_B, LABELLED_CORPUS, "quality-b")
    _seed(service, TENANT_A_USER_2, LABELLED_CORPUS, "quality-a2")

    own_texts = {text for text, _ in LABELLED_CORPUS}
    leaked = 0
    with bound_context(**TENANT_A):
        for _, query in LABELLED_CORPUS:
            for memory in service.get_relevant_memories({"text": query, "limit": 8})["memories"]:
                # Every tenant seeded identical text, so a leak is only visible
                # through the owner the memory actually belongs to.
                if memory["owner_id"] != TENANT_A["user_id"]:
                    leaked += 1
                assert memory["content"]["text"] in own_texts

    assert leaked == 0


def test_reseeding_the_corpus_adds_no_duplicate_active_memories():
    service, database, _ = _build()
    _seed(service, TENANT_A, LABELLED_CORPUS, "quality-a")
    _seed(service, TENANT_A, LABELLED_CORPUS, "quality-a-again")

    active = [doc for doc in database["episodic_memories"].docs if doc["status"] == "active"]
    assert len(active) == len(LABELLED_CORPUS)
