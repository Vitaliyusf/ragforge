"""Per-turn metric fact documents backing the admin metrics tab.

Prometheus answers "how is the system behaving right now" but cannot answer
"show tenant X's ten worst-groundedness turns last week" without exploding
label cardinality. Every turn therefore also writes one flat document to the
`metrics_turn_facts` collection, which admin queries aggregate over.

Tenancy: admin metrics are tenant-wide, so this module deliberately does not
reuse `conversation_persistence._scope()`, which also pins `owner_user_id`.
Writes take the tenant from the trusted request context. Reads (phase 2) must
assert `identity.is_admin` before dropping the `owner_user_id` boundary.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import RAGConfig
from app.services.conversation_types import ConversationRequest, utc_now_iso
from shared.auth import identity_from_context

try:
    from pymongo import MongoClient
    from pymongo.collection import Collection
    _HAS_PYMONGO = True
except ImportError:  # pragma: no cover - exercised by fallback tests
    MongoClient = None
    Collection = Any
    _HAS_PYMONGO = False


HIGH_CONFIDENCE_GROUNDEDNESS = 0.8
MEDIUM_CONFIDENCE_GROUNDEDNESS = 0.5

# Which rank the top score is compared against for `score_gap`. A turn that
# returned fewer chunks than this has no gap to report — see `TurnFact`.
SCORE_GAP_RANK = 5

SECONDS_PER_DAY = 86_400


def _identity():
    required = os.getenv("INTERNAL_AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
    return identity_from_context(required=required)


def _tenant_scope(query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Scope a metrics query to the tenant only.

    Unlike `conversation_persistence._scope()` this applies no `owner_user_id`
    boundary: admin metrics span every user in the tenant.
    """
    identity = _identity()
    source = dict(query or {})
    if identity is None:
        return source
    boundary = {"tenant_id": identity.tenant_id}
    return boundary if not source else {"$and": [boundary, source]}


def confidence_level(groundedness: Optional[float]) -> Optional[str]:
    """Bucket a groundedness score into a high/medium/low confidence level.

    Returns None when no groundedness score is available, so an errored turn
    records no confidence rather than a misleading "low".
    """
    if groundedness is None:
        return None
    if groundedness >= HIGH_CONFIDENCE_GROUNDEDNESS:
        return "high"
    if groundedness >= MEDIUM_CONFIDENCE_GROUNDEDNESS:
        return "medium"
    return "low"


def _optional_float(value: Any) -> Optional[float]:
    """Coerce to float, preserving None rather than turning it into 0.0."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    """Coerce to int, preserving None rather than turning it into 0."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TurnFact(BaseModel):
    """One conversation turn flattened for admin metric aggregation.

    Every quality field is optional on purpose. A turn that fails before
    retrieval or evaluation genuinely has no score, and writing zeros would
    silently drag down every average shown on the metrics tab.

    `score_gap` is the top score minus the fifth-ranked score — a proxy for how
    discriminative retrieval was, where a wide gap means one clearly best chunk
    and a flat one means the top result was arbitrary. It is None when the turn
    returned fewer than `SCORE_GAP_RANK` scored chunks: the gap to a rank that
    does not exist is unmeasured, and substituting 0.0 would report the
    flattest possible retrieval for what was often the sharpest.

    The citation fields — `citation_count`, `cited_chunk_ratio`,
    `citation_precision`, `citation_recall` — are populated from the answer's
    real inline citations and the judge's claim analysis. They stay None
    whenever that measurement did not happen: citations disabled, the judge
    unavailable, or nothing retrieved. `citation_precision` is also None for
    an answer that cited nothing, which is a different failure from citing
    badly and must not be averaged in as a zero.

    `hallucination_verdict` is None for every turn written before phase 6.
    Aggregations must count those turns separately rather than reading a
    missing verdict as "none" — see `metrics_query.quality`.
    """

    turn_id: str
    conversation_id: str
    tenant_id: Optional[str] = None
    ts: str
    mode: str
    latency_ms: float
    ttft_ms: Optional[float] = None
    stage_ms: Dict[str, float] = Field(default_factory=dict)
    chunk_count: int = 0
    top_score: Optional[float] = None
    mean_score: Optional[float] = None
    score_gap: Optional[float] = None
    reranker_changed_top1: Optional[bool] = None
    groundedness: Optional[float] = None
    completeness: Optional[float] = None
    safety: Optional[float] = None
    confidence: Optional[str] = None
    citation_count: Optional[int] = None
    cited_chunk_ratio: Optional[float] = None
    citation_precision: Optional[float] = None
    citation_recall: Optional[float] = None
    unsupported_claim_count: Optional[int] = None
    hallucination_verdict: Optional[str] = None
    guardrail_blocked: Optional[bool] = None
    revised: Optional[bool] = None
    model: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    error_class: Optional[str] = None


def build_turn_fact(
    request: ConversationRequest,
    result: Dict[str, Any],
    timings: Dict[str, Any],
) -> TurnFact:
    """Build the fact document for one finished turn.

    Pure: it reads its three arguments and the wall clock, and touches nothing
    else. All I/O lives in `MetricsFactStore`.

    Args:
        request: The normalized request that entered the graph.
        result: The graph result — `answer`, `sources`, `review`, and `error`
            on the failure path.
        timings: Observations collected by the graph while the turn ran:
            `latency_ms`, `ttft_ms`, `stage_ms`, `reranker_changed_top1`,
            `guardrail_blocked`, `model`, `usage`, and `error_class`.
            The citation figures come from `result["citation_metrics"]`,
            which the graph computes from the answer's citations and the
            internal review — claim text never reaches this module.

    Returns:
        TurnFact: The document to persist. Quality fields stay None whenever
        the turn produced no real measurement for them.
    """
    review = result.get("review") or {}
    sources = result.get("sources") or []
    citations = result.get("citation_metrics") or {}
    scores = [
        score
        for score in (
            _optional_float(chunk.get("score"))
            for chunk in sources
            if isinstance(chunk, dict)
        )
        if score is not None
    ]
    ranked = sorted(scores, reverse=True)
    usage = timings.get("usage") or {}
    stage_ms = {
        str(stage): float(elapsed)
        for stage, elapsed in (timings.get("stage_ms") or {}).items()
    }

    return TurnFact(
        turn_id=request.turn_id,
        conversation_id=request.conversation_id,
        tenant_id=request.tenant_id,
        ts=utc_now_iso(),
        mode=request.mode,
        latency_ms=float(timings.get("latency_ms") or 0.0),
        ttft_ms=_optional_float(timings.get("ttft_ms")),
        stage_ms=stage_ms,
        chunk_count=len(sources),
        top_score=max(scores) if scores else None,
        mean_score=(sum(scores) / len(scores)) if scores else None,
        score_gap=(
            ranked[0] - ranked[SCORE_GAP_RANK - 1] if len(ranked) >= SCORE_GAP_RANK else None
        ),
        reranker_changed_top1=timings.get("reranker_changed_top1"),
        groundedness=_optional_float(review.get("groundedness_score")),
        completeness=_optional_float(review.get("completeness_score")),
        safety=_optional_float(review.get("safety_score")),
        confidence=confidence_level(_optional_float(review.get("groundedness_score"))),
        citation_count=_optional_int(citations.get("citation_count")),
        cited_chunk_ratio=_optional_float(citations.get("cited_chunk_ratio")),
        citation_precision=_optional_float(citations.get("citation_precision")),
        citation_recall=_optional_float(citations.get("citation_recall")),
        unsupported_claim_count=_optional_int(review.get("unsupported_claim_count")),
        hallucination_verdict=review.get("hallucination_verdict"),
        guardrail_blocked=timings.get("guardrail_blocked"),
        revised=bool(review["revision_applied"]) if "revision_applied" in review else None,
        model=timings.get("model"),
        tokens_in=_optional_int(usage.get("input_tokens")),
        tokens_out=_optional_int(usage.get("output_tokens")),
        error_class=timings.get("error_class"),
    )


class MetricsFactStore:
    """Tenant-scoped persistence for per-turn metric facts.

    Falls back to an in-memory list when the service is configured for
    in-memory storage or pymongo is unavailable, so tests and local runs never
    need a broker.
    """

    def __init__(self, config: RAGConfig):
        self.config = config
        self.facts: List[Dict[str, Any]] = []
        self._in_memory = (
            config.conversation_store_type.lower() == "in_memory" or not _HAS_PYMONGO
        )
        self._client: Optional[MongoClient] = None
        self._db = None

    def _init_db(self) -> None:
        if self._db is not None:
            return
        last_error: Optional[Exception] = None
        for _ in range(self.config.mongodb_max_retries):
            try:
                self._client = MongoClient(self.config.mongodb_url)
                self._db = self._client[self.config.mongodb_database]
                return
            except Exception as exc:  # pragma: no cover - depends on env
                last_error = exc
                time.sleep(self.config.mongodb_retry_delay)
        raise RuntimeError(f"Failed to initialize MongoDB: {last_error}")

    def _collection(self) -> Collection:
        self._init_db()
        return self._db[self.config.metrics_turn_facts_collection]

    def ensure_indexes(self) -> None:
        """Create the tenant/time index and the retention TTL index."""
        if self._in_memory:
            return
        self._collection().create_index(
            [("tenant_id", 1), ("ts", -1)],
            name="idx_metrics_turn_facts_tenant_ts",
        )
        self._collection().create_index(
            [("ts", 1)],
            expireAfterSeconds=self.config.metrics_retention_days * SECONDS_PER_DAY,
            name="idx_metrics_turn_facts_ttl",
        )

    def save_fact(self, fact: TurnFact) -> None:
        """Persist one turn fact under the caller's tenant."""
        self._collection_insert(self._document(fact))

    def aggregate(
        self,
        pipeline: List[Dict[str, Any]],
        *,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run an aggregation pipeline over a metrics-readable collection.

        Returns an empty list in in-memory mode: that backend is a plain
        list with no aggregation engine, so a developer running without
        MongoDB sees empty panels rather than a crash or an invented number.

        Args:
            pipeline: A MongoDB aggregation pipeline. Its first stage must
                already carry the tenant boundary — see
                `MetricsQueryService`, which is the only caller.
            collection: Collection to read, defaulting to the turn-fact
                collection. Reads share this object's Mongo client rather
                than opening a second connection.

        Returns:
            The aggregation result rows.
        """
        if self._in_memory:
            return []
        self._init_db()
        name = collection or self.config.metrics_turn_facts_collection
        return list(self._db[name].aggregate(pipeline))

    def _document(self, fact: TurnFact) -> Dict[str, Any]:
        """Serialize a fact, stamping the tenant from the trusted context.

        `ts` is written as a BSON date rather than the model's ISO string: a
        MongoDB TTL index only expires documents on a real date field, and a
        TTL index over a string would silently retain everything forever.
        """
        document = fact.model_dump()
        identity = _identity()
        if identity is not None:
            document["tenant_id"] = identity.tenant_id
        document["ts"] = _parse_ts(fact.ts)
        return document

    def _collection_insert(self, document: Dict[str, Any]) -> None:
        if self._in_memory:
            self.facts.append(document)
            return
        self._collection().insert_one(document)


def _parse_ts(value: str) -> datetime:
    """Parse an ISO timestamp into a timezone-aware datetime."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def create_metrics_fact_store(config: RAGConfig) -> MetricsFactStore:
    """Create the metrics fact store for the configured backend."""
    return MetricsFactStore(config)
