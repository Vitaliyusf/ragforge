"""Tenant-scoped MongoDB aggregation behind the admin metrics tab.

Prometheus answers "how is the system behaving right now". These pipelines
answer the questions Prometheus cannot without exploding label cardinality:
per-tenant quality distributions, retrieval behaviour, token spend, and the
individual turns that scored worst.

Security invariants, all enforced here rather than left to callers:

- Every public method calls :func:`_require_admin` before touching Mongo.
- The tenant boundary lives in the pipeline's **first** ``$match`` stage, so
  a tenant never reaches Python only to be filtered out afterwards.
- This module deliberately does not reuse ``conversation_persistence._scope``,
  which also pins ``owner_user_id``. Admin metrics are tenant-wide, spanning
  every user in the tenant — but never more than one tenant. A platform-wide
  "all tenants" view is out of scope.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.config import RAGConfig
from app.services.metrics_facts import MetricsFactStore
from shared.auth import AuthIdentity, identity_from_context

# Mirrors ``RagAction.GET_METRICS`` in the gateway's app/core/constants.py.
# The rag service cannot import gateway code, so the literal is defined once
# here; the two must stay in step.
METRICS_ACTION = "get_metrics"

# rag's own allow-list. It matches the gateway's ``MetricsWindow`` enum, but
# an RPC caller is not automatically the gateway, so the value is validated
# again on arrival rather than trusted.
WINDOW_SECONDS: Dict[str, int] = {
    "1h": 3_600,
    "24h": 86_400,
    "7d": 604_800,
    "30d": 2_592_000,
}

DEFAULT_WINDOW = "24h"
DEFAULT_WORST_TURN_LIMIT = 10
MAX_WORST_TURN_LIMIT = 50

# Upper bound is above 1.0 because $bucket treats the last boundary as
# exclusive, and a perfect 1.0 score must land in the top bucket.
SCORE_BOUNDARIES: List[float] = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
CHUNK_BOUNDARIES: List[int] = [0, 1, 3, 5, 8, 13, 21]

# The rating values the answer-feedback control actually emits.
POSITIVE_RATING = "positive"
NEGATIVE_RATING = "negative"
ANSWER_FEEDBACK_TYPE = "answer_feedback"

ALL_SECTIONS = ("overview", "quality", "retrieval", "cost", "worst_turns")


class MetricsAccessDenied(PermissionError):
    """The caller is not an administrator of the tenant being queried."""


class MetricsWindowInvalid(ValueError):
    """The caller supplied a window outside the allow-list."""


def _require_admin() -> AuthIdentity:
    """Return the calling identity, or refuse if it is not an admin.

    Strict by design: an absent identity is refused as firmly as a
    non-admin one. These pipelines drop the per-user ownership boundary, so
    there is no safe way to run them for an unidentified caller.

    Raises:
        MetricsAccessDenied: If no identity is bound, or it is not an admin.
    """
    identity = identity_from_context(required=False)
    if identity is None or not identity.is_admin:
        raise MetricsAccessDenied("Administrator role required for metrics queries")
    return identity


def _validate_window(window: Optional[str]) -> str:
    """Validate a window against the allow-list.

    Raises:
        MetricsWindowInvalid: If ``window`` is not an allowed value.
    """
    resolved = window or DEFAULT_WINDOW
    if resolved not in WINDOW_SECONDS:
        raise MetricsWindowInvalid(f"Unsupported metrics window: {window!r}")
    return resolved


def _ratio(numerator: float, denominator: float) -> Optional[float]:
    """Divide, returning None rather than 0.0 when there is nothing to divide.

    A rate over zero turns is unknown, not zero. Returning 0.0 would put a
    confident-looking "0% error rate" on a tab that has no data at all.
    """
    if not denominator:
        return None
    return numerator / denominator


def _first(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the single row of a ``_id: None`` group, or an empty dict."""
    return rows[0] if rows else {}


def _bucket_label(lower: Any, boundaries: List[Any]) -> str:
    """Render one ``$bucket`` key as a human-readable range label."""
    if lower not in boundaries:
        return str(lower)
    index = boundaries.index(lower)
    if index + 1 >= len(boundaries):
        return f"{lower}+"
    return f"{lower}-{boundaries[index + 1]}"


def _histogram(rows: List[Dict[str, Any]], boundaries: List[Any]) -> List[Dict[str, Any]]:
    """Convert ``$bucket`` output into ordered ``{bucket, count}`` entries."""
    return [
        {"bucket": _bucket_label(row.get("_id"), boundaries), "count": row.get("count", 0)}
        for row in rows
    ]


class MetricsQueryService:
    """Aggregate ``metrics_turn_facts`` for one tenant's admin metrics tab."""

    def __init__(self, config: RAGConfig, store: MetricsFactStore) -> None:
        self.config = config
        self.store = store

    # ------------------------------------------------------------------
    # Scoping
    # ------------------------------------------------------------------

    def _match(
        self,
        window: str,
        tenant_id: Optional[str],
        identity: AuthIdentity,
    ) -> Dict[str, Any]:
        """Build the tenant-and-time predicate for a pipeline's first stage.

        An explicit ``tenant_id`` must equal the caller's own tenant. Reading
        another tenant's metrics is not a feature of this phase, and letting
        an admin do it by passing a string would make it one.

        Raises:
            MetricsAccessDenied: If ``tenant_id`` names a different tenant.
        """
        if tenant_id is not None and tenant_id != identity.tenant_id:
            raise MetricsAccessDenied("Cross-tenant metrics access denied")
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS[window])
        return {"tenant_id": identity.tenant_id, "ts": {"$gte": cutoff}}

    def _feedback_match(
        self,
        window: str,
        identity: AuthIdentity,
    ) -> Dict[str, Any]:
        """Build the first ``$match`` for the answer-feedback collection.

        Feedback documents store ``created_at`` as an ISO-8601 string from
        ``utc_now_iso()``, not a BSON date, so the cutoff is compared as a
        string. That is correct here only because every value is UTC with
        the same fixed-width format, making lexical and chronological order
        the same.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS[window])
        return {
            "tenant_id": identity.tenant_id,
            "feedback_type": ANSWER_FEEDBACK_TYPE,
            "created_at": {"$gte": cutoff.isoformat()},
        }

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def overview(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return headline counts, means, and quality KPIs for the window.

        Args:
            window: A key of :data:`WINDOW_SECONDS`.
            tenant_id: The tenant to report on. Defaults to the caller's.

        Returns:
            A flat dict of KPI values. Any rate over zero turns is None.
        """
        identity = _require_admin()
        window = _validate_window(window)
        pipeline = [
            {"$match": self._match(window, tenant_id, identity)},
            {
                "$group": {
                    "_id": None,
                    "turns": {"$sum": 1},
                    "errored_turns": {
                        "$sum": {"$cond": [{"$ne": ["$error_class", None]}, 1, 0]}
                    },
                    "turns_with_chunks": {
                        "$sum": {"$cond": [{"$gt": ["$chunk_count", 0]}, 1, 0]}
                    },
                    "mean_latency_ms": {"$avg": "$latency_ms"},
                    "mean_ttft_ms": {"$avg": "$ttft_ms"},
                    "mean_groundedness": {"$avg": "$groundedness"},
                    "mean_completeness": {"$avg": "$completeness"},
                    "mean_safety": {"$avg": "$safety"},
                    "mean_chunk_count": {"$avg": "$chunk_count"},
                    "tokens_in": {"$sum": {"$ifNull": ["$tokens_in", 0]}},
                    "tokens_out": {"$sum": {"$ifNull": ["$tokens_out", 0]}},
                }
            },
        ]
        row = _first(self.store.aggregate(pipeline))
        turns = row.get("turns", 0)
        feedback = self._feedback_counts(window, identity)
        return {
            "turns": turns,
            "errored_turns": row.get("errored_turns", 0),
            "error_rate": _ratio(row.get("errored_turns", 0), turns),
            "retrieval_hit_rate": _ratio(row.get("turns_with_chunks", 0), turns),
            "mean_latency_ms": row.get("mean_latency_ms"),
            "mean_ttft_ms": row.get("mean_ttft_ms"),
            "mean_groundedness": row.get("mean_groundedness"),
            "mean_completeness": row.get("mean_completeness"),
            "mean_safety": row.get("mean_safety"),
            "mean_chunk_count": row.get("mean_chunk_count"),
            "tokens_in": row.get("tokens_in", 0),
            "tokens_out": row.get("tokens_out", 0),
            **feedback,
        }

    def quality(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return score distributions, confidence mix, and quality rates.

        Citation coverage is deliberately absent: ``citation_count`` and
        ``cited_chunk_ratio`` are always None until phase 6, because the app
        emits no citations yet.

        Returns:
            A dict whose hallucination figure is named
            ``hallucination_rate_proxy_groundedness`` and is accompanied by
            the threshold that defines it. It is a threshold over a single
            judge score, not a claim-level measurement.
        """
        identity = _require_admin()
        window = _validate_window(window)
        threshold = self.config.hallucination_groundedness_threshold
        pipeline = [
            {"$match": self._match(window, tenant_id, identity)},
            {
                "$facet": {
                    "groundedness_histogram": self._score_facet("groundedness"),
                    "completeness_histogram": self._score_facet("completeness"),
                    "safety_histogram": self._score_facet("safety"),
                    "confidence": [
                        {"$group": {"_id": "$confidence", "count": {"$sum": 1}}},
                        {"$sort": {"_id": 1}},
                    ],
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "turns": {"$sum": 1},
                                "scored_turns": {
                                    "$sum": {
                                        "$cond": [{"$ne": ["$groundedness", None]}, 1, 0]
                                    }
                                },
                                "below_threshold": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {"$ne": ["$groundedness", None]},
                                                    {"$lt": ["$groundedness", threshold]},
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "revision_evaluated": {
                                    "$sum": {"$cond": [{"$ne": ["$revised", None]}, 1, 0]}
                                },
                                "revised": {
                                    "$sum": {"$cond": [{"$eq": ["$revised", True]}, 1, 0]}
                                },
                                "guardrail_evaluated": {
                                    "$sum": {
                                        "$cond": [{"$ne": ["$guardrail_blocked", None]}, 1, 0]
                                    }
                                },
                                "guardrail_blocked": {
                                    "$sum": {
                                        "$cond": [{"$eq": ["$guardrail_blocked", True]}, 1, 0]
                                    }
                                },
                                "mean_groundedness": {"$avg": "$groundedness"},
                            }
                        }
                    ],
                }
            },
        ]
        facets = _first(self.store.aggregate(pipeline))
        totals = _first(facets.get("totals") or [])
        return {
            "turns": totals.get("turns", 0),
            "scored_turns": totals.get("scored_turns", 0),
            "mean_groundedness": totals.get("mean_groundedness"),
            "groundedness_histogram": _histogram(
                facets.get("groundedness_histogram") or [], SCORE_BOUNDARIES
            ),
            "completeness_histogram": _histogram(
                facets.get("completeness_histogram") or [], SCORE_BOUNDARIES
            ),
            "safety_histogram": _histogram(
                facets.get("safety_histogram") or [], SCORE_BOUNDARIES
            ),
            "confidence_mix": [
                {"level": row.get("_id"), "count": row.get("count", 0)}
                for row in (facets.get("confidence") or [])
            ],
            "hallucination_rate_proxy_groundedness": _ratio(
                totals.get("below_threshold", 0), totals.get("scored_turns", 0)
            ),
            "hallucination_groundedness_threshold": threshold,
            "revision_rate": _ratio(
                totals.get("revised", 0), totals.get("revision_evaluated", 0)
            ),
            "guardrail_block_rate": _ratio(
                totals.get("guardrail_blocked", 0), totals.get("guardrail_evaluated", 0)
            ),
            **self._feedback_counts(window, identity),
        }

    def retrieval(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return hit rate, score and chunk histograms, and reranker lift."""
        identity = _require_admin()
        window = _validate_window(window)
        pipeline = [
            {"$match": self._match(window, tenant_id, identity)},
            {
                "$facet": {
                    "top_score_histogram": self._score_facet("top_score"),
                    "chunks_per_query": [
                        {
                            "$bucket": {
                                "groupBy": "$chunk_count",
                                "boundaries": CHUNK_BOUNDARIES,
                                "default": "21+",
                                "output": {"count": {"$sum": 1}},
                            }
                        }
                    ],
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "turns": {"$sum": 1},
                                "turns_with_chunks": {
                                    "$sum": {"$cond": [{"$gt": ["$chunk_count", 0]}, 1, 0]}
                                },
                                "empty_retrievals": {
                                    "$sum": {"$cond": [{"$eq": ["$chunk_count", 0]}, 1, 0]}
                                },
                                "mean_chunk_count": {"$avg": "$chunk_count"},
                                "mean_top_score": {"$avg": "$top_score"},
                                "mean_score": {"$avg": "$mean_score"},
                                "reranker_evaluated": {
                                    "$sum": {
                                        "$cond": [
                                            {"$ne": ["$reranker_changed_top1", None]}, 1, 0
                                        ]
                                    }
                                },
                                "reranker_changed": {
                                    "$sum": {
                                        "$cond": [
                                            {"$eq": ["$reranker_changed_top1", True]}, 1, 0
                                        ]
                                    }
                                },
                            }
                        }
                    ],
                }
            },
        ]
        facets = _first(self.store.aggregate(pipeline))
        totals = _first(facets.get("totals") or [])
        turns = totals.get("turns", 0)
        return {
            "turns": turns,
            "hit_rate": _ratio(totals.get("turns_with_chunks", 0), turns),
            "empty_retrieval_rate": _ratio(totals.get("empty_retrievals", 0), turns),
            "mean_chunk_count": totals.get("mean_chunk_count"),
            "mean_top_score": totals.get("mean_top_score"),
            "mean_score": totals.get("mean_score"),
            "top_score_histogram": _histogram(
                facets.get("top_score_histogram") or [], SCORE_BOUNDARIES
            ),
            "chunks_per_query": _histogram(
                facets.get("chunks_per_query") or [], CHUNK_BOUNDARIES
            ),
            "reranker_changed_top1_rate": _ratio(
                totals.get("reranker_changed", 0), totals.get("reranker_evaluated", 0)
            ),
            "reranker_evaluated_turns": totals.get("reranker_evaluated", 0),
        }

    def cost(self, window: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Return token sums grouped by model.

        No price is applied here. The cost table lives in the gateway's
        ``MODEL_COST_PER_1K_TOKENS``, and the gateway turns these token sums
        into ``estimated_cost_usd`` — one source of truth for pricing rather
        than a second copy in this service that could drift from it.
        """
        identity = _require_admin()
        window = _validate_window(window)
        pipeline = [
            {"$match": self._match(window, tenant_id, identity)},
            {
                "$group": {
                    "_id": "$model",
                    "turns": {"$sum": 1},
                    "tokens_in": {"$sum": {"$ifNull": ["$tokens_in", 0]}},
                    "tokens_out": {"$sum": {"$ifNull": ["$tokens_out", 0]}},
                }
            },
            {"$sort": {"tokens_out": -1}},
        ]
        rows = self.store.aggregate(pipeline)
        by_model = [
            {
                "model": row.get("_id"),
                "turns": row.get("turns", 0),
                "tokens_in": row.get("tokens_in", 0),
                "tokens_out": row.get("tokens_out", 0),
            }
            for row in rows
        ]
        return {
            "by_model": by_model,
            "tokens_in": sum(item["tokens_in"] for item in by_model),
            "tokens_out": sum(item["tokens_out"] for item in by_model),
        }

    def worst_turns(
        self,
        window: str,
        tenant_id: Optional[str] = None,
        limit: int = DEFAULT_WORST_TURN_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Return the lowest-groundedness turns in the window.

        Identifiers and scores only. No message or answer text leaves this
        method — an operational metrics tab does not need to reproduce
        conversation content to show which turns scored badly.
        """
        identity = _require_admin()
        window = _validate_window(window)
        capped = max(1, min(int(limit or DEFAULT_WORST_TURN_LIMIT), MAX_WORST_TURN_LIMIT))
        match = self._match(window, tenant_id, identity)
        match["groundedness"] = {"$ne": None}
        pipeline = [
            {"$match": match},
            {"$sort": {"groundedness": 1}},
            {"$limit": capped},
            {
                "$project": {
                    "_id": 0,
                    "turn_id": 1,
                    "conversation_id": 1,
                    "ts": 1,
                    "groundedness": 1,
                    "completeness": 1,
                    "safety": 1,
                    "confidence": 1,
                }
            },
        ]
        return [self._serialize_turn(row) for row in self.store.aggregate(pipeline)]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run the requested sections for one RPC request.

        A route needing several sections asks for them together, so each
        gateway route costs one RPC rather than one per panel.

        Args:
            payload: The RPC business payload. Recognised keys are
                ``sections`` (a list, defaulting to every section),
                ``window``, ``tenant_id``, and ``limit``.

        Returns:
            A dict keyed by section name. On refusal or an invalid window it
            carries an ``error`` key, which the reply envelope turns into an
            unsuccessful reply.
        """
        requested = payload.get("sections") or list(ALL_SECTIONS)
        window = payload.get("window")
        tenant_id = payload.get("tenant_id")
        limit = payload.get("limit") or DEFAULT_WORST_TURN_LIMIT

        try:
            # The tenant echoed here is the one the pipelines actually ran
            # against, not the one the caller typed. The gateway reports it
            # verbatim, so the response can never claim a tenant it did not
            # read.
            result: Dict[str, Any] = {"tenant_id": _require_admin().tenant_id}
            for section in requested:
                if section == "worst_turns":
                    result[section] = self.worst_turns(window, tenant_id, limit)
                elif section in ALL_SECTIONS:
                    result[section] = getattr(self, section)(window, tenant_id)
            return result
        except (MetricsAccessDenied, MetricsWindowInvalid) as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_facet(field: str) -> List[Dict[str, Any]]:
        """Build a ``$facet`` branch bucketing one 0-1 score field."""
        return [
            {"$match": {field: {"$ne": None}}},
            {
                "$bucket": {
                    "groupBy": f"${field}",
                    "boundaries": SCORE_BOUNDARIES,
                    "default": "out_of_range",
                    "output": {"count": {"$sum": 1}},
                }
            },
        ]

    def _feedback_counts(self, window: str, identity: AuthIdentity) -> Dict[str, Any]:
        """Return thumbs-up/down counts and rate from the feedback collection.

        The rating vocabulary (``positive`` / ``negative``) is what the
        answer-feedback control actually submits; nothing else is inferred.
        """
        pipeline = [
            {"$match": self._feedback_match(window, identity)},
            {"$group": {"_id": "$payload.rating", "count": {"$sum": 1}}},
        ]
        rows = self.store.aggregate(
            pipeline, collection=self.config.user_feedback_collection
        )
        counts = {row.get("_id"): row.get("count", 0) for row in rows}
        positive = counts.get(POSITIVE_RATING, 0)
        negative = counts.get(NEGATIVE_RATING, 0)
        return {
            "thumbs_up": positive,
            "thumbs_down": negative,
            "thumbs_up_rate": _ratio(positive, positive + negative),
        }

    @staticmethod
    def _serialize_turn(row: Dict[str, Any]) -> Dict[str, Any]:
        """Make one projected turn JSON-safe for the RPC reply envelope."""
        serialized = dict(row)
        timestamp = serialized.get("ts")
        if isinstance(timestamp, datetime):
            serialized["ts"] = timestamp.isoformat()
        return serialized
