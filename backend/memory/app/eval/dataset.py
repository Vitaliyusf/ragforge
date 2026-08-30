"""Authoritative synthetic labels for the deterministic memory benchmark.

Labels are produced by this generator before any Memory service or agent code
runs.  The generator contains no calls to those systems and uses no external
model, so a system output can never silently become its own ground truth.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DATASET_VERSION = "memory-eval.synthetic.v1"
DATASET_SEED = 20260830
DEFAULT_SCENARIO_COUNT = 624
LANGUAGES = ("en", "he", "mixed")


@dataclass(frozen=True)
class MemoryScenario:
    """One fully labelled, isolated memory evaluation scenario."""

    scenario_id: str
    tenant_id: str
    user_id: str
    turns: Tuple[Mapping[str, str], ...]
    language: str
    tags: Tuple[str, ...]
    difficulty: str
    seed_memories: Tuple[Mapping[str, Any], ...]
    candidate: Optional[Mapping[str, Any]]
    expected_candidate_ids: Tuple[str, ...]
    proposed_candidate_ids: Tuple[str, ...]
    expected_action: str
    expected_active_ids: Tuple[str, ...]
    expected_inactive_ids: Tuple[str, ...]
    retrieval_queries: Tuple[Mapping[str, Any], ...]
    expected_trajectory: Tuple[str, ...]
    allowed_trajectories: Tuple[Tuple[str, ...], ...]
    forbidden_actions: Tuple[str, ...]
    delete_authorized: bool
    agent_plan: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _text(language: str, variant: int, value: str = "PostgreSQL") -> str:
    entity = f"Orion-{variant:02d}"
    if language == "he":
        return f"הפרויקט {entity} משתמש ב-{value} בסביבת הייצור."
    if language == "mixed":
        return f"הפרויקט {entity} uses {value} in production."
    return f"Project {entity} uses {value} in production."


def _turn(language: str, variant: int, text: Optional[str] = None) -> Mapping[str, str]:
    return {"role": "user", "content": text or _text(language, variant)}


def _memory(
    label: str,
    text: str,
    *,
    fact_key: Optional[str] = None,
    scope: Optional[Mapping[str, str]] = None,
    event_at: str = "2026-03-01T00:00:00+00:00",
    valid_to: Optional[str] = None,
    confidence: float = 0.9,
) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "label": label,
        "content": {"text": text},
        "event_at": event_at,
        "importance": 0.85,
        "confidence": confidence,
        "provenance": {"explicit_user_signal": True, "synthetic": True},
    }
    if fact_key:
        value["fact_key"] = fact_key
    if scope:
        value["scope"] = dict(scope)
    if valid_to:
        value["valid_to"] = valid_to
    return value


def _query(
    text: str,
    expected: Sequence[str] = (),
    *,
    forbidden: Sequence[str] = (),
    stale: Sequence[str] = (),
    abstain: bool = False,
    include_history: bool = False,
    as_of: Optional[str] = None,
    graded: Optional[Mapping[str, int]] = None,
    scope: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    return {
        "text": text,
        "expected_ids": list(expected),
        "forbidden_ids": list(forbidden),
        "stale_ids": list(stale),
        "expected_abstention": abstain,
        "include_history": include_history,
        "as_of": as_of,
        "graded_relevance": dict(graded or {item: 1 for item in expected}),
        "scope": dict(scope or {}),
    }


def _scenario(family: str, variant: int, language: str) -> MemoryScenario:
    scenario_id = f"{family}-{variant:03d}-{language}"
    fact_key = f"deployment_store_{variant:03d}"
    old = _memory("old", _text(language, variant, "PostgreSQL"), fact_key=fact_key)
    new = _memory(
        "new",
        _text(language, variant, "CockroachDB"),
        fact_key=fact_key,
        event_at="2026-05-01T00:00:00+00:00",
    )
    query = f"Orion-{variant:02d} production database"
    seed: Tuple[Mapping[str, Any], ...] = ()
    candidate: Optional[Mapping[str, Any]] = new
    turns: Tuple[Mapping[str, str], ...] = (_turn(language, variant),)
    expected_candidates: Tuple[str, ...] = ("new",)
    proposed_candidates: Tuple[str, ...] = ("new",)
    action = "create"
    active: Tuple[str, ...] = ("new",)
    inactive: Tuple[str, ...] = ()
    queries: Tuple[Mapping[str, Any], ...] = (_query(query, ("new",)),)
    trajectory: Tuple[str, ...] = ("search_memory", "compare_existing", "create_memory")
    allowed: Tuple[Tuple[str, ...], ...] = (trajectory,)
    forbidden: Tuple[str, ...] = ("delete_memory",)
    delete_authorized = False
    plan: Mapping[str, Any] = {
        "actions": [{"action": "create", "content": new["content"]["text"]}],
        "summary": family,
    }
    difficulty = "medium"
    tags = [family]

    if family == "durable_preference":
        candidate = _memory("new", f"User prefers concise answers for Orion-{variant:02d}.", fact_key=f"preference_{variant}")
        turns = (_turn(language, variant, candidate["content"]["text"]),)
        queries = (_query(f"Orion-{variant:02d} answer preference", ("new",)),)
        tags.append("preference")
    elif family == "project_context":
        tags.append("project")
    elif family == "stable_fact":
        tags.append("stable-fact")
    elif family in {"irrelevant_chatter", "temporary_plan", "assistant_only_inference"}:
        role = "assistant" if family == "assistant_only_inference" else "user"
        content = {
            "irrelevant_chatter": "Thanks, that is all for now.",
            "temporary_plan": "I might have lunch downtown today.",
            "assistant_only_inference": "The user probably prefers Rust.",
        }[family]
        turns = ({"role": role, "content": content},)
        candidate = None
        expected_candidates = ()
        proposed_candidates = ()
        action = "no_op"
        active = ()
        queries = (_query("lasting user preference", abstain=True),)
        trajectory = ("search_memory", "compare_existing", "ignore")
        allowed = (trajectory, ("search_memory", "ignore"))
        plan = {"actions": [{"action": "ignore", "reason": family}], "summary": family}
        tags.append("no-memory")
    elif family == "low_confidence_rejection":
        candidate = _memory("new", _text(language, variant), fact_key=fact_key, confidence=0.2)
        expected_candidates = ()
        proposed_candidates = ("new",)
        action = "no_op"
        active = ()
        queries = (_query(query, abstain=True),)
        trajectory = ("search_memory", "compare_existing", "no_mutation_fallback")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "create", "content": candidate["content"]["text"], "confidence": 0.2}], "summary": family}
        tags.extend(("no-memory", "low-confidence"))
    elif family == "exact_duplicate":
        seed = (old,)
        candidate = dict(old, label="duplicate")
        action = "duplicate_exact"
        active = ("old",)
        expected_candidates = ("duplicate",)
        proposed_candidates = ("duplicate",)
        queries = (_query(query, ("old",)),)
        trajectory = ("search_memory", "compare_existing", "ignore")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "ignore", "reason": "duplicate"}], "summary": family}
        tags.append("duplicate")
    elif family == "semantic_duplicate":
        seed = (old,)
        candidate = _memory(
            "duplicate",
            old["content"]["text"] + " Primary.",
            fact_key=fact_key,
        )
        action = "duplicate_semantic"
        active = ("old",)
        expected_candidates = ("duplicate",)
        proposed_candidates = ("duplicate",)
        queries = (_query(query, ("old",)),)
        trajectory = ("search_memory", "compare_existing", "ignore")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "ignore", "reason": "semantic duplicate"}], "summary": family}
        tags.append("duplicate")
    elif family in {"correction", "temporal_update", "explicit_update"}:
        seed = (old,)
        action = "update" if family == "explicit_update" else "supersede"
        active = ("new",)
        inactive = ("old",)
        queries = (_query(query, ("new",), stale=("old",)),)
        if family == "temporal_update":
            queries += (_query(query, ("old",), include_history=True, as_of="2026-04-01T00:00:00+00:00"),)
            tags.append("temporal")
        agent_action = "update" if family == "explicit_update" else "supersede"
        trajectory = ("search_memory", "compare_existing", f"{agent_action}_memory")
        allowed = (trajectory,)
        plan = {"actions": [{"action": agent_action, "memory_id": "existing-1", "content": new["content"]["text"]}], "summary": family}
        tags.append("conflict")
    elif family == "ambiguous_contradiction":
        seed = (_memory("old", _text(language, variant, "PostgreSQL")),)
        candidate = _memory("new", _text(language, variant, "CockroachDB"))
        action = "needs_review"
        active = ("old", "new")
        queries = (_query(query, ("old", "new"), graded={"new": 2, "old": 1}),)
        trajectory = ("search_memory", "compare_existing", "merge_suggestion")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "merge_suggestion", "memory_id": "existing-1", "reason": "ambiguous"}], "summary": family}
        tags.append("conflict")
    elif family == "stale_history":
        seed = (old,)
        candidate = _memory("historical", _text(language, variant, "SQLite"), fact_key=fact_key, event_at="2025-01-01T00:00:00+00:00", valid_to="2025-12-31T00:00:00+00:00")
        action = "historical"
        active = ("old",)
        inactive = ("historical",)
        queries = (
            _query(query, ("old",), stale=("historical",)),
            _query(query, ("historical",), include_history=True, as_of="2025-06-01T00:00:00+00:00"),
        )
        tags.extend(("temporal", "stale"))
    elif family == "scope_coexistence":
        seed = (old,)
        candidate = _memory("new", _text(language, variant, "CockroachDB"), fact_key=fact_key, scope={"environment": "staging"})
        action = "coexist"
        active = ("old", "new")
        queries = (_query(query, ("old", "new"), graded={"old": 2, "new": 1}),)
        tags.append("scope")
    elif family == "valid_scope_update":
        staging_old = _memory(
            "old",
            _text(language, variant, "PostgreSQL"),
            fact_key=fact_key,
            scope={"environment": "staging"},
        )
        production = _memory(
            "other",
            _text(language, variant, "MySQL"),
            fact_key=fact_key,
            scope={"environment": "production"},
        )
        seed = (staging_old, production)
        candidate = _memory(
            "new",
            _text(language, variant, "CockroachDB"),
            fact_key=fact_key,
            scope={"environment": "staging"},
        )
        action = "supersede"
        active = ("new", "other")
        inactive = ("old",)
        queries = (
            _query(
                query,
                ("new",),
                stale=("old",),
                scope={"environment": "staging"},
            ),
        )
        trajectory = ("search_memory", "compare_existing", "supersede_memory")
        allowed = (trajectory,)
        plan = {
            "actions": [
                {
                    "action": "supersede",
                    "memory_id": "existing-1",
                    "content": candidate["content"]["text"],
                }
            ],
            "summary": family,
        }
        tags.append("scope")
    elif family in {"deletion", "resurrection_attempt"}:
        seed = (old,)
        candidate = None if family == "deletion" else dict(old, label="resurrected")
        expected_candidates = () if family == "deletion" else ("resurrected",)
        proposed_candidates = expected_candidates
        action = "delete" if family == "deletion" else "resurrection_prevented"
        active = ()
        inactive = ("old",)
        queries = (_query(query, forbidden=("old", "resurrected"), abstain=True),)
        delete_authorized = True
        trajectory = ("search_memory", "compare_existing", "delete_memory") if family == "deletion" else ("search_memory", "compare_existing", "ignore")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "delete", "memory_id": "existing-1"}], "summary": family} if family == "deletion" else {"actions": [{"action": "ignore", "reason": "deleted tombstone"}], "summary": family}
        forbidden = () if family == "deletion" else ("create_memory", "delete_memory")
        tags.append("deletion")
    elif family == "multi_turn_evidence":
        turns = (
            _turn(language, variant, f"We are discussing Orion-{variant:02d}."),
            {"role": "assistant", "content": "Which database does it use?"},
            _turn(language, variant, "It uses PostgreSQL in production, please remember that."),
        )
        tags.append("multi-turn")
    elif family in {"tenant_collision", "user_collision"}:
        tags.append("tenant-isolation" if family == "tenant_collision" else "user-isolation")
    elif family == "unauthorized_candidate_id":
        seed = (old,)
        candidate = None
        expected_candidates = ()
        proposed_candidates = ()
        action = "no_op"
        active = ("old",)
        queries = (_query(query, ("old",)),)
        trajectory = ("search_memory", "compare_existing", "no_mutation_fallback")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "update", "memory_id": "foreign-id", "content": new["content"]["text"]}], "summary": family}
        tags.append("adversarial")
    elif family == "destructive_action_attempt":
        seed = (old,)
        candidate = None
        expected_candidates = ()
        proposed_candidates = ()
        action = "no_op"
        active = ("old",)
        queries = (_query(query, ("old",)),)
        trajectory = ("search_memory", "compare_existing", "no_mutation_fallback")
        allowed = (trajectory,)
        plan = {"actions": [{"action": "delete", "memory_id": "existing-1"}], "summary": family}
        tags.append("adversarial")
    elif family == "retry_idempotency":
        action = "idempotent"
        tags.append("idempotency")
    elif family == "partial_vector_reconciliation":
        action = "create"
        tags.append("reconciliation")
    elif family == "cross_language_retrieval":
        candidate = _memory("new", f"פרויקט Orion-{variant:02d} משתמש ב-PostgreSQL בייצור.", fact_key=fact_key)
        turns = (_turn("he", variant, candidate["content"]["text"]),)
        queries = (_query(f"Which production database does Orion-{variant:02d} use PostgreSQL", ("new",)),)
        tags.extend(("cross-language", "hebrew"))
        difficulty = "hard"

    return MemoryScenario(
        scenario_id=scenario_id,
        tenant_id=f"tenant-{variant % 4}",
        user_id=f"user-{variant % 7}",
        turns=turns,
        language=language,
        tags=tuple(tags),
        difficulty=difficulty,
        seed_memories=seed,
        candidate=candidate,
        expected_candidate_ids=expected_candidates,
        proposed_candidate_ids=proposed_candidates,
        expected_action=action,
        expected_active_ids=active,
        expected_inactive_ids=inactive,
        retrieval_queries=queries,
        expected_trajectory=trajectory,
        allowed_trajectories=allowed,
        forbidden_actions=forbidden,
        delete_authorized=delete_authorized,
        agent_plan=plan,
    )


FAMILIES = (
    "durable_preference",
    "project_context",
    "stable_fact",
    "irrelevant_chatter",
    "temporary_plan",
    "exact_duplicate",
    "semantic_duplicate",
    "correction",
    "temporal_update",
    "explicit_update",
    "ambiguous_contradiction",
    "stale_history",
    "scope_coexistence",
    "deletion",
    "resurrection_attempt",
    "multi_turn_evidence",
    "assistant_only_inference",
    "low_confidence_rejection",
    "tenant_collision",
    "user_collision",
    "unauthorized_candidate_id",
    "destructive_action_attempt",
    "retry_idempotency",
    "partial_vector_reconciliation",
    "cross_language_retrieval",
    "valid_scope_update",
)


def generate_scenarios(count: int = DEFAULT_SCENARIO_COUNT) -> List[MemoryScenario]:
    """Return a stable scenario pack; ``count`` must retain family coverage."""
    if count < len(FAMILIES):
        raise ValueError(f"count must be at least {len(FAMILIES)}")
    scenarios = [
        _scenario(family, cycle, LANGUAGES[(cycle + family_index) % len(LANGUAGES)])
        for cycle in range(1, (count + len(FAMILIES) - 1) // len(FAMILIES) + 1)
        for family_index, family in enumerate(FAMILIES)
    ][:count]
    random.Random(DATASET_SEED).shuffle(scenarios)
    return scenarios


def canonical_dataset_bytes(scenarios: Iterable[MemoryScenario]) -> bytes:
    payload = [scenario.to_dict() for scenario in scenarios]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def dataset_manifest(scenarios: Sequence[MemoryScenario]) -> Dict[str, Any]:
    payload = canonical_dataset_bytes(scenarios)
    languages: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    for scenario in scenarios:
        languages[scenario.language] = languages.get(scenario.language, 0) + 1
        for tag in scenario.tags:
            categories[tag] = categories.get(tag, 0) + 1
    return {
        "dataset_version": DATASET_VERSION,
        "dataset_sha256": hashlib.sha256(payload).hexdigest(),
        "seed": DATASET_SEED,
        "scenario_count": len(scenarios),
        "languages": dict(sorted(languages.items())),
        "categories": dict(sorted(categories.items())),
        "synthetic_only": True,
    }


def split_scenarios(scenarios: Sequence[MemoryScenario], split: str) -> List[MemoryScenario]:
    sizes = {"smoke": 40, "quick": 100, "standard": 250, "full": len(scenarios)}
    if split in sizes:
        return list(scenarios[: sizes[split]])
    return [scenario for scenario in scenarios if split in scenario.tags]
