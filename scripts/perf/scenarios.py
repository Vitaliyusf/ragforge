"""The nine request classes CONC-00 measures, and how to drive each one.

A scenario is a *declaration* plus a driver factory. The declaration — name,
transport, what it exercises, whether a driver can reach it — is available
without a running stack, which is what lets the harness emit an honest
artifact from a machine with Docker stopped: every class appears, and the ones
that could not be measured are marked ``deferred`` with the reason.

**Reachability is a fact about the topology, not an opinion.** The default
Compose file publishes only gateway (8000) and rag (8004) to localhost;
embedding and vector_db expose HTTP on the internal networks only, and the
embedding query/ingestion paths are RabbitMQ RPC and Kafka rather than HTTP at
all. Those classes therefore carry a ``deferred_reason`` unless the operator
supplies a reachable URL explicitly with ``--service-url``. Emitting a
plausible-looking zero for them would be exactly the fabricated performance
claim the task forbids.

**Fallback is detected, never assumed.** A scenario that can tell a degraded
answer from a healthy one says so through ``classify``; the driver reports
``fallback`` and the artifact keeps it separate from ``success``. A chat that
asked for RAG and came back with ``use_rag: false`` did not succeed at what it
was measuring.

**Read paths by default.** The baseline must be re-runnable without
corrupting product state, so the default profile set drives reads and chat
turns. Ingestion classes write, and are opt-in through ``--include-writes``
with a dedicated tenant/dataset supplied by the operator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

# Transports, so an artifact reader can tell an HTTP number from an RPC one.
TRANSPORT_HTTP = "http"
TRANSPORT_RABBITMQ_RPC = "rabbitmq_rpc"
TRANSPORT_KAFKA = "kafka"

# Logical targets resolved to base URLs by the CLI. Only the first two are
# reachable from the host under the default Compose topology.
TARGET_GATEWAY = "gateway"
TARGET_RAG = "rag"
TARGET_EMBEDDING = "embedding"
TARGET_VECTOR_DB = "vector_db"

_NOT_PUBLISHED = (
    "{service} publishes no host-reachable port in the default Compose "
    "topology; pass --service-url {target}=<url> from inside the Compose "
    "network to measure it"
)

_NOT_HTTP = (
    "{service} serves this class over {transport}, not HTTP; a broker-side "
    "driver is required and is deferred to {owner}"
)


@dataclass(frozen=True)
class HttpCall:
    """An HTTP request shape a scenario repeats under load."""

    method: str
    path: str
    # Built per call index so a scenario can vary its payload deterministically
    # — the same index must always produce the same request, or two baseline
    # runs are not comparable.
    body: Optional[Callable[[int], Dict[str, Any]]] = None
    params: Optional[Callable[[int], Dict[str, Any]]] = None


@dataclass(frozen=True)
class ScenarioSpec:
    """One measured request class."""

    name: str
    description: str
    transport: str
    target: str
    http: Optional[HttpCall] = None
    # Returns "success" or "fallback" for a 2xx response. Default: any 2xx is
    # a plain success, because a scenario that cannot see degradation must not
    # claim there was none either way.
    classify: Optional[Callable[[Any], str]] = None
    # Non-None means this class has no driver reachable from the harness host.
    deferred_reason: Optional[str] = None
    # Writes product state; excluded unless the operator opts in.
    mutates_state: bool = False
    limitations: Tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "transport": self.transport,
            "target": self.target,
            "mutates_state": self.mutates_state,
            "limitations": list(self.limitations),
        }


def _chat_body(message: str, *, use_rag: bool, answer_mode: str) -> Callable[[int], Dict[str, Any]]:
    def build(index: int) -> Dict[str, Any]:
        # The index is in the message so every call is a distinct turn — an
        # identical repeated prompt would measure whatever cache sits in front
        # of the model rather than the pipeline.
        return {
            "message": f"{message} (baseline probe {index})",
            "use_rag": use_rag,
            "answer_mode": answer_mode,
        }

    return build


def _rag_actually_ran(payload: Any) -> str:
    """A RAG turn that came back without RAG fell back to the plain LLM."""
    if isinstance(payload, Mapping) and payload.get("use_rag") is False:
        return "fallback"
    return "success"


def _rag_returned_sources(payload: Any) -> str:
    """Extended retrieval that returned no sources degraded to a bare answer."""
    if isinstance(payload, Mapping):
        if payload.get("use_rag") is False:
            return "fallback"
        sources = payload.get("sources")
        if isinstance(sources, list) and not sources:
            return "fallback"
    return "success"


SCENARIOS: Tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        name="gateway_chat_plain",
        description="Gateway chat with RAG disabled: gateway → LLM agent RPC → vLLM.",
        transport=TRANSPORT_HTTP,
        target=TARGET_GATEWAY,
        http=HttpCall("POST", "/v1/chat", body=_chat_body("Summarize your capabilities.", use_rag=False, answer_mode="quick")),
    ),
    ScenarioSpec(
        name="gateway_chat_rag",
        description="Gateway chat with RAG enabled, quick answer mode: the full regular pipeline.",
        transport=TRANSPORT_HTTP,
        target=TARGET_GATEWAY,
        http=HttpCall("POST", "/v1/chat", body=_chat_body("What do the indexed documents cover?", use_rag=True, answer_mode="quick")),
        classify=_rag_actually_ran,
    ),
    ScenarioSpec(
        name="rag_extended",
        description="Extended retrieval: second retrieval pass, reranking and the longer answer path.",
        transport=TRANSPORT_HTTP,
        target=TARGET_GATEWAY,
        http=HttpCall("POST", "/v1/chat", body=_chat_body("Explain the indexed material in depth.", use_rag=True, answer_mode="extended")),
        classify=_rag_returned_sources,
        limitations=(
            "a 'fallback' here can mean either a reranker that answered busy or "
            "a genuinely empty retrieval; the reranker_status_total metric "
            "separates the two on the service side",
        ),
    ),
    ScenarioSpec(
        name="embedding_query",
        description="Single-query embedding over the RabbitMQ RPC path.",
        transport=TRANSPORT_RABBITMQ_RPC,
        target=TARGET_EMBEDDING,
        deferred_reason=_NOT_HTTP.format(
            service="embedding", transport="RabbitMQ RPC", owner="CHECKPOINT B"
        ),
    ),
    ScenarioSpec(
        name="embedding_ingestion",
        description="Batch embedding of an ingestion job consumed from Kafka.",
        transport=TRANSPORT_KAFKA,
        target=TARGET_EMBEDDING,
        mutates_state=True,
        deferred_reason=_NOT_HTTP.format(
            service="embedding", transport="a Kafka job topic", owner="CHECKPOINT B"
        ),
    ),
    ScenarioSpec(
        name="vector_search",
        description="Dense and hybrid chunk search against Qdrant.",
        transport=TRANSPORT_HTTP,
        target=TARGET_VECTOR_DB,
        http=HttpCall("POST", "/api/v1/chunks/search"),
        deferred_reason=_NOT_PUBLISHED.format(service="vector_db", target=TARGET_VECTOR_DB),
        limitations=(
            "requires a query vector of the deployed embedding dimension; the "
            "operator supplies it with --vector-query-file",
        ),
    ),
    ScenarioSpec(
        name="memory_operation",
        description="Long-term memory read through the gateway.",
        transport=TRANSPORT_HTTP,
        target=TARGET_GATEWAY,
        http=HttpCall("GET", "/v1/long-term-memory"),
    ),
    ScenarioSpec(
        name="file_ingestion",
        description="File upload and the handoff into the ingestion pipeline.",
        transport=TRANSPORT_HTTP,
        target=TARGET_GATEWAY,
        http=HttpCall("POST", "/v1/files/upload"),
        mutates_state=True,
        limitations=(
            "each measured call creates a document; run against a disposable "
            "tenant and expect to clean up afterwards",
        ),
    ),
    ScenarioSpec(
        name="eval_background",
        description="Eval/benchmark execution running as a background task in rag.",
        transport=TRANSPORT_HTTP,
        target=TARGET_RAG,
        mutates_state=True,
        deferred_reason=(
            "an eval run is a long background job, not a request; measuring it "
            "under a concurrency ladder needs the job-level driver deferred to "
            "CONC-99's load campaign"
        ),
    ),
)

SCENARIOS_BY_NAME: Dict[str, ScenarioSpec] = {spec.name: spec for spec in SCENARIOS}


def read_only_scenarios() -> Tuple[ScenarioSpec, ...]:
    """Scenarios safe to run repeatedly without changing product state."""
    return tuple(spec for spec in SCENARIOS if not spec.mutates_state)
