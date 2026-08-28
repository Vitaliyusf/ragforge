"""Pass1/Pass2 retrieval: bounding, determinism, global ranking, eligibility and chunk search."""
from __future__ import annotations

import asyncio

import pytest
from shared.context import get_context

from app.core.config import RAGConfig
from app.services.conversation_backend_client import ConversationBackendClient
from app.services.conversation_events import CollectingConversationEmitter
from app.services.retrieval_trace import STAGE_MERGED, RetrievalTrace
from app.tests._service_harness import (
    TEST_IDENTITY,
    CaptureServiceClient,
    build_service,
)


def test_extended_pass_one_retrieval_is_bounded_and_deterministic():
    service, backend, _ = build_service()
    service.graph_runner.config.extended_retrieval_max_concurrency = 2
    service.graph_runner.config.pass_two_chunk_threshold = 1
    service.graph_runner.config.pass_two_score_threshold = 0.1
    queries = ["rewrite", "slow subquery", "fast subquery", "last subquery"]
    delays = {
        "rewrite": 0.04,
        "slow subquery": 0.03,
        "fast subquery": 0.01,
        "last subquery": 0.0,
    }
    active = 0
    max_active = 0
    saw_overlap = asyncio.Event()
    propagated = []

    async def rewrite(request, context):
        return {"rewritten_query": queries[0], "subqueries": queries[1:]}

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        nonlocal active, max_active
        assert pass_name == "pass_one"
        active += 1
        max_active = max(max_active, active)
        if active > 1:
            saw_overlap.set()
        propagated.append(
            (
                request.request_id,
                request.trace_id,
                get_context().get("tenant_id"),
                retrieval_plan["rewritten_query"],
            )
        )
        try:
            await asyncio.sleep(delays[query])
        finally:
            active -= 1
        return {
            "chunks": [
                {
                    "chunk_id": query,
                    "text": query,
                    "score": 0.8,
                    "source": f"{query}.md",
                }
            ]
        }

    backend.query_rewrite = rewrite
    backend.search_chunks = search_chunks
    request = service.build_request({"question": "parallelize", "mode": "extended"})
    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    assert saw_overlap.is_set()
    assert max_active == 2
    assert [chunk["chunk_id"] for chunk in result["sources"]] == queries
    assert propagated == [
        (request.request_id, request.trace_id, TEST_IDENTITY.tenant_id, queries[0])
    ] * len(queries)



def test_extended_parallel_retrieval_preserves_downstream_error_policy():
    service, backend, _ = build_service()
    service.graph_runner.config.extended_retrieval_max_concurrency = 2

    async def rewrite(request, context):
        return {"rewritten_query": "ok", "subqueries": ["fails", "cancelled"]}

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        if query == "fails":
            await asyncio.sleep(0.01)
            raise ValueError("subquery retrieval failed")
        await asyncio.sleep(0.03)
        return {
            "chunks": [
                {"chunk_id": query, "text": query, "score": 0.8, "source": "source.md"}
            ]
        }

    backend.query_rewrite = rewrite
    backend.search_chunks = search_chunks
    request = service.build_request({"question": "parallelize", "mode": "extended"})
    result = asyncio.run(
        service.graph_runner.run(request, CollectingConversationEmitter(request))
    )

    assert result["outcome"] == "failed"
    assert result["error"] == "subquery retrieval failed"
    assert result["error_class"] == "ValueError"
    assert result["failed_node"] == "retrieve_pass_one"
    assert result["sources"] == []



def test_pass_two_candidates_are_globally_ranked_and_deduped():
    service, backend, _ = build_service()
    service.graph_runner.config.top_k_documents = 2

    async def search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        backend.calls.append({"type": "vector_db", "pass_name": pass_name, "query": query})
        if pass_name == "pass_two":
            return {
                "chunks": [
                    {"chunk_id": "c1", "text": "Duplicate", "score": 0.5, "source": "one.md"},
                    {"chunk_id": "c2", "text": "Best Pass2", "score": 0.95, "source": "two.md"},
                    {"chunk_id": "c4", "text": "Tied Pass2", "score": 0.7, "source": "four.md"},
                ]
            }
        return {
            "chunks": [
                {"chunk_id": "c1", "text": "Best duplicate", "score": 0.8, "source": "one.md"},
                {"chunk_id": "c3", "text": "Tied Pass1", "score": 0.7, "source": "three.md"},
            ]
        }

    backend.search_chunks = search_chunks
    request = service.build_request(
        {"question": "Need second retrieval and revise this answer", "mode": "extended"}
    )
    emitter = CollectingConversationEmitter(request)
    trace = RetrievalTrace()

    result = asyncio.run(
        service.graph_runner.run(request, emitter, retrieval_trace=trace)
    )

    chunk_ids = [chunk["chunk_id"] for chunk in result["sources"]]
    merged = next(stage for stage in trace.stages if stage["stage"] == STAGE_MERGED)
    assert [item["chunk_id"] for item in merged["candidates"]] == ["c2", "c1", "c3", "c4"]
    assert chunk_ids == ["c2", "c1"]
    assert chunk_ids.count("c1") == 1
    assert result["sources"][1]["score"] == 0.8



def test_search_chunks_embeds_query_before_vector_search():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(
        responses=[
            {"embedding": [0.1, 0.2, 0.3]},
            {"results": [{"id": "chunk-1", "score": 0.9, "payload": {"chunk_id": "chunk-1"}}]},
        ]
    )
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    response = asyncio.run(backend.search_chunks(request, "hello", {"decision": "rewrite"}, "pass_one"))

    assert response["results"][0]["payload"]["chunk_id"] == "chunk-1"
    assert len(service_client.calls) == 2

    embedding_call = service_client.calls[0]
    assert embedding_call["routing_key"] == "embedding"
    assert embedding_call["payload"]["action"] == "embed"
    assert embedding_call["payload"]["payload"]["text"] == "hello"

    vector_call = service_client.calls[1]
    assert vector_call["routing_key"] == "vector_db"
    envelope = vector_call["payload"]
    assert envelope["message_type"] == "query"
    assert envelope["action"] == "search_chunks"
    assert envelope["payload"]["query_vector"] == [0.1, 0.2, 0.3]
    assert envelope["payload"]["query"] == "hello"
    assert envelope["payload"]["pass_name"] == "pass_one"
    # Production retrieval keeps the configured answer-context depth: the
    # eval harness's wider candidate depth must not leak into a user turn.
    assert envelope["payload"]["top_k"] == config.top_k_documents
    assert "reply_to" not in envelope



def test_search_chunks_top_k_can_be_overridden_for_an_eval_sweep():
    """The retrieval eval must be able to ask beyond `top_k_documents`.

    Recall@20 is only a measurement if twenty candidates were requested;
    raising `top_k_documents` to get there would change what every user turn
    is answered from.
    """
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(
        responses=[{"embedding": [0.1, 0.2, 0.3]}, {"results": []}]
    )
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    asyncio.run(backend.search_chunks(request, "hello", {}, "eval", top_k=20))

    assert config.top_k_documents == 6
    assert service_client.calls[1]["payload"]["payload"]["top_k"] == 20



def test_search_chunks_raises_when_embedding_reply_is_empty():
    config = RAGConfig(conversation_store_type="in_memory", enable_langsmith_tracing=False)
    service_client = CaptureServiceClient(response={"embedding": []})
    backend = ConversationBackendClient(config, service_client)
    service, _, _ = build_service()
    request = service.build_request({"question": "hello"})

    with pytest.raises(RuntimeError, match="returned no query_vector"):
        asyncio.run(backend.search_chunks(request, "hello"))



def test_retrieval_filters_ineligible_chunks():
    service, backend, _ = build_service()

    async def fake_search_chunks(request, query, retrieval_plan=None, pass_name="pass_one"):
        backend.calls.append({"type": "vector_db", "pass_name": pass_name, "query": query})
        return {
            "chunks": [
                {"chunk_id": "good", "text": "Keep me", "score": 0.8, "source": "good.md", "review_status": "clean", "retrieval_allowed": True},
                {"chunk_id": "removed", "text": "Drop me", "score": 0.95, "source": "bad.md", "review_status": "removed", "retrieval_allowed": True},
                {"chunk_id": "blocked", "text": "Also drop me", "score": 0.7, "source": "blocked.md", "review_status": "clean", "retrieval_allowed": False},
            ]
        }

    backend.search_chunks = fake_search_chunks
    request = service.build_request({"question": "Filter chunks", "mode": "regular"})
    emitter = CollectingConversationEmitter(request)

    asyncio.run(service.graph_runner.run(request, emitter))

    done_event = emitter.events[-1]
    source_ids = [chunk["chunk_id"] for chunk in done_event["data"]["sources"]]
    assert source_ids == ["good"]



