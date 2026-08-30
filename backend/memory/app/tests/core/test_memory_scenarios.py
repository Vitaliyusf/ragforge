"""A labelled scenario pack for consolidation, conflict and reconciliation.

Every scenario names the outcome it expects before the code runs, so the
numbers reported for MEMORY-V2-02 come from labels rather than from whatever
the implementation happened to do. Similarity comes from the bag-of-words
measurement stub, which is a real if weak semantic model: it makes the ranking
meaningful without pretending to be the production embedding model.
"""

from typing import Any, Dict, List

from shared.context import bound_context

from app.services.memory_consolidation import (
    OUTCOME_COEXIST,
    OUTCOME_CREATE,
    OUTCOME_DUPLICATE_EXACT,
    OUTCOME_DUPLICATE_SEMANTIC,
    OUTCOME_NEEDS_REVIEW,
    OUTCOME_SUPERSEDE,
)
from app.tests._memory_harness import (
    BagOfWordsEmbeddingClient,
    InMemoryVectorIndex,
    build_memory_service,
    build_reconciliation_service,
)

TENANT_A = dict(tenant_id="tenant-a", user_id="user-1", role="user")
TENANT_B = dict(tenant_id="tenant-b", user_id="user-9", role="user")

GCP = "The project deploys to GCP."
AWS = "The project deploys to AWS."
BILLING = "The team uses Postgres for billing."
BILLING_LONGER = "The team uses Postgres for billing storage."
HIRING = "The user hired two backend engineers for the payments team."

# Each scenario seeds some memories, writes one more, and names what that last
# write must do and how many active memories the owner should be left with.
SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "exact-duplicate",
        "seed": [{"text": GCP}],
        "candidate": {"text": GCP},
        "outcome": OUTCOME_DUPLICATE_EXACT,
        "active": 1,
    },
    {
        "id": "exact-duplicate-different-casing",
        "seed": [{"text": GCP}],
        "candidate": {"text": "the project DEPLOYS to gcp."},
        "outcome": OUTCOME_DUPLICATE_EXACT,
        "active": 1,
    },
    {
        "id": "semantic-duplicate",
        "seed": [{"text": BILLING}],
        "candidate": {"text": BILLING_LONGER},
        "outcome": OUTCOME_DUPLICATE_SEMANTIC,
        "active": 1,
    },
    {
        "id": "explicit-contradiction",
        "seed": [{"text": GCP, "fact_key": "deployment_target"}],
        "candidate": {"text": AWS, "fact_key": "deployment_target"},
        "outcome": OUTCOME_SUPERSEDE,
        "active": 1,
    },
    {
        "id": "temporal-update",
        "seed": [{"text": GCP, "fact_key": "deployment_target", "event_at": "2026-01-01T00:00:00+00:00"}],
        "candidate": {"text": AWS, "fact_key": "deployment_target", "event_at": "2026-04-01T00:00:00+00:00"},
        "outcome": OUTCOME_SUPERSEDE,
        "active": 1,
    },
    {
        "id": "valid-coexistence",
        "seed": [{"text": GCP, "fact_key": "deployment_target"}],
        "candidate": {"text": AWS, "fact_key": "deployment_target", "scope": {"environment": "new"}},
        "outcome": OUTCOME_COEXIST,
        "active": 2,
    },
    {
        "id": "scoped-update",
        "seed": [
            {"text": GCP, "fact_key": "deployment_target"},
            {"text": AWS, "fact_key": "deployment_target", "scope": {"environment": "new"}},
        ],
        "candidate": {
            "text": "The project deploys to Azure.",
            "fact_key": "deployment_target",
            "scope": {"environment": "new"},
        },
        "outcome": OUTCOME_SUPERSEDE,
        "active": 2,
    },
    {
        "id": "ambiguous-related-fact",
        "seed": [{"text": GCP}],
        "candidate": {"text": AWS},
        "outcome": OUTCOME_NEEDS_REVIEW,
        "active": 2,
    },
    {
        "id": "unrelated-fact",
        "seed": [{"text": GCP}],
        "candidate": {"text": HIRING},
        "outcome": OUTCOME_CREATE,
        "active": 2,
    },
]


def _candidate(spec):
    candidate = {
        "content": {"text": spec["text"]},
        "event_at": spec.get("event_at", "2026-03-01T00:00:00+00:00"),
        "importance": 0.8,
        "confidence": 0.8,
        "provenance": {"explicit_user_signal": True},
    }
    for key in ("fact_key", "scope", "valid_to", "supersedes"):
        if key in spec:
            candidate[key] = spec[key]
    return candidate


def _service():
    return build_memory_service(
        index_client=InMemoryVectorIndex(),
        embedding_client=BagOfWordsEmbeddingClient(),
    )


def _run_scenario(scenario, identity=TENANT_A):
    service, database, _ = _service()
    with bound_context(**identity):
        for index, spec in enumerate(scenario["seed"]):
            service.write_memory(
                _candidate(spec),
                {"owner_type": "user", "request_id": f"{scenario['id']}-seed-{index}"},
            )
        result = service.write_memory(
            _candidate(scenario["candidate"]),
            {"owner_type": "user", "request_id": f"{scenario['id']}-final"},
        )
    active = [doc for doc in database["episodic_memories"].docs if doc["status"] == "active"]
    return service, database, result, active


def test_every_labelled_scenario_reaches_its_expected_outcome():
    mismatches = []
    for scenario in SCENARIOS:
        _, _, result, active = _run_scenario(scenario)
        outcome = result["consolidation"]["outcome"]
        if outcome != scenario["outcome"] or len(active) != scenario["active"]:
            mismatches.append(
                {
                    "id": scenario["id"],
                    "expected": (scenario["outcome"], scenario["active"]),
                    "actual": (outcome, len(active)),
                }
            )

    assert mismatches == []


def test_no_scenario_leaves_two_active_memories_for_one_fact_and_scope():
    collisions = []
    for scenario in SCENARIOS:
        _, _, _, active = _run_scenario(scenario)
        seen = set()
        for doc in active:
            if not doc.get("fact_key"):
                continue
            key = (doc["fact_key"], doc.get("scope_key", ""))
            if key in seen:
                collisions.append((scenario["id"], key))
            seen.add(key)

    assert collisions == []


def test_a_superseded_scenario_keeps_its_history_readable():
    service, database, result, _ = _run_scenario(SCENARIOS[3])

    superseded = [doc for doc in database["episodic_memories"].docs if doc["status"] == "superseded"]
    with bound_context(**TENANT_A):
        current = service.get_relevant_memories({"text": "deployment target", "limit": 5})
        history = service.get_relevant_memories(
            {"text": "deployment target", "limit": 5, "include_history": True}
        )

    assert len(superseded) == 1
    assert superseded[0]["valid_to"] is not None
    assert [memory["content"]["text"] for memory in current["memories"]] == [AWS]
    assert GCP in [memory["content"]["text"] for memory in history["memories"]]
    assert result["superseded_memory_id"] == superseded[0]["id"]


def test_the_scenario_pack_leaks_nothing_across_tenants():
    leaked = 0
    for scenario in SCENARIOS:
        service, database, _, _ = _run_scenario(scenario)
        # Replay the same scenario for a second tenant against the same
        # storage: identical text on both sides is the case a filter bug hides
        # behind.
        with bound_context(**TENANT_B):
            for index, spec in enumerate(scenario["seed"] + [scenario["candidate"]]):
                service.write_memory(
                    _candidate(spec),
                    {"owner_type": "user", "request_id": f"{scenario['id']}-b-{index}"},
                )
        with bound_context(**TENANT_A):
            visible = service.get_relevant_memories(
                {"text": "deployment project team", "limit": 20, "include_history": True}
            )
        leaked += sum(
            1
            for memory in visible["memories"]
            if memory["owner_id"] != TENANT_A["user_id"]
        )
        leaked += sum(
            1
            for doc in database["episodic_memories"].docs
            if doc["tenant_id"] == "tenant-b" and doc["id"] in {m["id"] for m in visible["memories"]}
        )

    assert leaked == 0


def test_the_scenario_pack_reconciles_to_a_clean_index():
    unresolved = []
    repaired = 0
    for scenario in SCENARIOS:
        service, _, _, _ = _run_scenario(scenario)
        with bound_context(**TENANT_A):
            reconciler = build_reconciliation_service(service)
            report = reconciler.reconcile()
            # A second pass over already-clean state must find nothing.
            second = reconciler.reconcile()
        repaired += report["repaired"]
        unresolved.extend(report["unresolved"])
        assert second["repaired"] == 0
        assert sum(second["drift"].values()) == 0

    assert unresolved == []
    assert repaired == 0
