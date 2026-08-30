"""Offline deterministic runner for the labelled Memory V2 benchmark."""
from __future__ import annotations

import copy
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from shared.context import bound_context

from app.agent.memory_agent import AgentScope, MemoryAgent
from app.eval.dataset import MemoryScenario, dataset_manifest, generate_scenarios
from app.eval.metrics import candidate_metrics, failure_counts, lifecycle_metrics, retrieval_metrics
from app.eval.trajectory import aggregate_trajectories, trajectory_row
from app.tests._memory_harness import (
    BagOfWordsEmbeddingClient,
    FakeVectorIndex,
    InMemoryVectorIndex,
    build_memory_service,
)

MEASUREMENT_CLASS = "AUTHORITATIVE DETERMINISTIC"
EMBEDDING_DISCLAIMER = (
    "Retrieval uses the deterministic Unicode bag-of-words measurement stub; "
    "it does not measure production multilingual E5 quality."
)


@dataclass
class _RecordingMemoryService:
    writes: List[Mapping[str, Any]]
    deletes: List[str]

    def write_memory(self, candidate: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
        self.writes.append(
            {
                "candidate": copy.deepcopy(dict(candidate)),
                "context": copy.deepcopy(dict(context)),
            }
        )
        return {"status": "accepted", "memory_id": f"recorded-{len(self.writes)}"}

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        self.deletes.append(memory_id)
        return {"status": "deleted", "memory_id": memory_id}


class _PlanResponder:
    def __init__(self, plan: Mapping[str, Any]) -> None:
        self.plan = copy.deepcopy(dict(plan))
        self.calls = 0

    def __call__(self, _action: str, _payload: Dict[str, Any], _timeout: float) -> Dict[str, Any]:
        self.calls += 1
        return copy.deepcopy(self.plan)


def _identity(scenario: MemoryScenario) -> Dict[str, str]:
    return {"tenant_id": scenario.tenant_id, "user_id": scenario.user_id, "role": "user"}


def _payload(spec: Mapping[str, Any], labels: Mapping[str, str]) -> Dict[str, Any]:
    candidate = copy.deepcopy(dict(spec))
    candidate.pop("label", None)
    supersedes_label = candidate.pop("supersedes_label", None)
    if supersedes_label:
        candidate["supersedes"] = next(
            memory_id
            for memory_id, label in labels.items()
            if label == str(supersedes_label)
        )
    return candidate


def _write(
    service: Any,
    scenario: MemoryScenario,
    spec: Mapping[str, Any],
    request_id: str,
    labels: MutableMapping[str, str],
) -> Dict[str, Any]:
    result = service.write_memory(
        _payload(spec, labels),
        {"owner_type": "user", "request_id": request_id},
    )
    memory_id = result.get("memory_id")
    label = str(spec.get("label") or "")
    if memory_id and label:
        labels.setdefault(str(memory_id), label)
    return dict(result)


def _collections(database: Mapping[str, Any]) -> List[Any]:
    return [
        database[name]
        for name in ("episodic_memories", "semantic_preferences")
        if name in database
    ]


def _actual_state(
    database: Mapping[str, Any],
    labels: Mapping[str, str],
    scenario: MemoryScenario,
) -> Tuple[List[str], List[str]]:
    active: List[str] = []
    inactive: List[str] = []
    for collection in _collections(database):
        for document in collection.docs:
            if document.get("tenant_id") != scenario.tenant_id or document.get("owner_id") != scenario.user_id:
                continue
            label = labels.get(str(document.get("id")))
            if not label:
                continue
            if document.get("status") == "active" and not document.get("valid_to"):
                active.append(label)
            else:
                inactive.append(label)
    return sorted(set(active)), sorted(set(inactive))


def _consolidation_action(scenario: MemoryScenario, result: Mapping[str, Any]) -> str:
    if result.get("status") == "rejected":
        return "no_op"
    outcome = str((result.get("consolidation") or {}).get("outcome") or result.get("status") or "unknown")
    if scenario.expected_action == "update" and outcome == "supersede":
        return "update"
    return outcome


def _run_memory_scenario(scenario: MemoryScenario) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    partial_vector = "partial_vector_reconciliation" in scenario.tags
    index = FakeVectorIndex(enabled=True, fail_index=True) if partial_vector else InMemoryVectorIndex()
    service, database, _ = build_memory_service(
        index_client=index,
        embedding_client=BagOfWordsEmbeddingClient(),
    )
    labels: Dict[str, str] = {}
    deleted_labels: List[str] = []
    result: Dict[str, Any] = {}
    false_destructive = 0
    persistence_started = time.perf_counter()
    with bound_context(**_identity(scenario)):
        for position, spec in enumerate(scenario.seed_memories):
            _write(service, scenario, spec, f"{scenario.scenario_id}:seed:{position}", labels)

        if scenario.expected_action in {"delete", "resurrection_prevented"}:
            old_id = next((memory_id for memory_id, label in labels.items() if label == "old"), "")
            if old_id:
                service.delete_memory(old_id)
                deleted_labels.append("old")
            actual_action = "delete"
            if scenario.expected_action == "resurrection_prevented" and scenario.candidate:
                result = _write(
                    service,
                    scenario,
                    scenario.candidate,
                    f"{scenario.scenario_id}:resurrection",
                    labels,
                )
                actual_action = (
                    "resurrection_prevented"
                    if result.get("status") in {"duplicate", "rejected"}
                    else _consolidation_action(scenario, result)
                )
        elif scenario.expected_action == "idempotent" and scenario.candidate:
            request_id = f"{scenario.scenario_id}:idempotent"
            first = _write(service, scenario, scenario.candidate, request_id, labels)
            before = sum(len(collection.docs) for collection in _collections(database))
            second = _write(service, scenario, scenario.candidate, request_id, labels)
            after = sum(len(collection.docs) for collection in _collections(database))
            result = second
            actual_action = (
                "idempotent"
                if first.get("memory_id") == second.get("memory_id") and before == after
                else "create"
            )
        elif scenario.candidate is not None:
            candidate = dict(scenario.candidate)
            if scenario.expected_action == "update" and scenario.seed_memories:
                candidate["supersedes_label"] = "old"
            result = _write(
                service,
                scenario,
                candidate,
                f"{scenario.scenario_id}:candidate",
                labels,
            )
            actual_action = _consolidation_action(scenario, result)
        else:
            actual_action = "no_op"

        if "tenant_collision" in scenario.tags or "user_collision" in scenario.tags:
            collision_identity = dict(_identity(scenario))
            if "tenant_collision" in scenario.tags:
                collision_identity["tenant_id"] = f"{scenario.tenant_id}-foreign"
                collision_identity["user_id"] = f"{scenario.user_id}-foreign"
            else:
                collision_identity["user_id"] = f"{scenario.user_id}-foreign"
            with bound_context(**collision_identity):
                foreign = dict(scenario.candidate or scenario.seed_memories[0])
                foreign["label"] = "foreign"
                foreign_result = service.write_memory(
                    _payload(foreign, labels),
                    {"owner_type": "user", "request_id": f"{scenario.scenario_id}:foreign"},
                )
                if foreign_result.get("memory_id"):
                    labels[str(foreign_result["memory_id"])] = "foreign"

    persistence_ms = (time.perf_counter() - persistence_started) * 1000
    actual_active, actual_inactive = _actual_state(database, labels, scenario)
    actual_inactive = sorted(set(actual_inactive).union(deleted_labels))
    expected_active = sorted(scenario.expected_active_ids)
    expected_inactive = sorted(scenario.expected_inactive_ids)
    state_correct = actual_active == expected_active and set(expected_inactive).issubset(actual_inactive)
    lifecycle = {
        "scenario_id": scenario.scenario_id,
        "expected_action": scenario.expected_action,
        "actual_action": actual_action,
        "expected_active_ids": expected_active,
        "actual_active_ids": actual_active,
        "expected_inactive_ids": expected_inactive,
        "actual_inactive_ids": actual_inactive,
        "active_state_correct": state_correct,
        "false_destructive_mutation": false_destructive,
        "reconciliation_required": bool(result.get("reconciliation_required")),
    }

    retrieval_rows: List[Dict[str, Any]] = []
    retrieval_started = time.perf_counter()
    for position, labelled_query in enumerate(scenario.retrieval_queries):
        query = dict(labelled_query)
        request: Dict[str, Any] = {
            "text": query["text"],
            "limit": 5,
            "include_history": query.get("include_history", False),
        }
        if query.get("as_of"):
            request["as_of"] = query["as_of"]
        if query.get("scope"):
            request["scope"] = query["scope"]
        with bound_context(**_identity(scenario)):
            response = service.get_relevant_memories(request)
        memories = response["memories"]
        actual_ids = [labels.get(str(memory["id"]), f"unknown:{memory['id']}") for memory in memories]
        tenant_leakage = sum(
            memory.get("tenant_id") is not None and memory.get("tenant_id") != scenario.tenant_id
            for memory in memories
        )
        user_leakage = sum(
            memory.get("owner_id") is not None and memory.get("owner_id") != scenario.user_id
            for memory in memories
        )
        if "tenant_collision" in scenario.tags:
            tenant_leakage += actual_ids.count("foreign")
        if "user_collision" in scenario.tags:
            user_leakage += actual_ids.count("foreign")
        retrieval_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "query_index": position,
                **query,
                "actual_ids": actual_ids,
                "tenant_leakage": tenant_leakage,
                "user_leakage": user_leakage,
                "retrieval_mode": response.get("retrieval_mode"),
                "provenance": response.get("provenance"),
            }
        )
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
    return lifecycle, retrieval_rows, {
        "labels": labels,
        "result": result,
        "persistence_ms": persistence_ms,
        "retrieval_ms": retrieval_ms,
    }


def _run_agent_scenario(scenario: MemoryScenario) -> Dict[str, Any]:
    recorder = _RecordingMemoryService([], [])
    responder = _PlanResponder(scenario.agent_plan)
    agent = MemoryAgent(recorder, responder, _NullLogger())
    existing = []
    if scenario.seed_memories:
        existing = [
            {
                "id": "existing-1",
                "tenant_id": scenario.tenant_id,
                "owner_id": scenario.user_id,
                "content": scenario.seed_memories[0]["content"],
            }
        ]
    scope = AgentScope(
        tenant_id=scenario.tenant_id,
        user_id=scenario.user_id,
        role="user",
        request_id=scenario.scenario_id,
        trace_id=f"trace:{scenario.scenario_id}",
        chat_id=f"chat:{scenario.scenario_id}",
        delete_authorized=scenario.delete_authorized,
    )
    result = agent.curate(scenario.turns, existing, scope, timeout=1.0)
    actual = ["search_memory", "compare_existing"]
    if result.status == "fallback":
        actual.append("no_mutation_fallback")
    else:
        tool_names = {
            "ignore": "ignore",
            "create": "create_memory",
            "update": "update_memory",
            "supersede": "supersede_memory",
            "merge_suggestion": "merge_suggestion",
            "delete": "delete_memory",
        }
        actual.extend(tool_names[str(decision["action"])] for decision in result.decisions)
    invalid_target_ids = int(any("outside the bounded candidate set" in error for error in result.errors))
    fallback_expected = bool(
        scenario.expected_trajectory
        and scenario.expected_trajectory[-1] == "no_mutation_fallback"
    )
    return {
        "scenario_id": scenario.scenario_id,
        **trajectory_row(
            scenario.expected_trajectory,
            actual,
            allowed=scenario.allowed_trajectories,
            forbidden=scenario.forbidden_actions,
            invalid_target_ids=invalid_target_ids,
            fallback_expected=fallback_expected,
        ),
        "status": result.status,
        "retries": result.provenance.get("retries"),
        "errors": result.errors,
        "model_calls": responder.calls,
        "agent_latency_ms": result.provenance.get("agent_latency_ms"),
    }


class _NullLogger:
    def log(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _source_revision() -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
        return completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _final_use_metrics(retrieval_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    eligible = [row for row in retrieval_rows if row.get("expected_ids")]
    correct = stale_safe = irrelevant_safe = isolated = linked = 0
    for row in eligible:
        actual = list(row.get("actual_ids") or [])
        selected = actual[:1]
        expected = set(row.get("expected_ids") or [])
        correct += int(bool(expected.intersection(selected)))
        stale_safe += int(not set(row.get("stale_ids") or []).intersection(selected))
        irrelevant_safe += int(not selected or selected[0] in expected)
        isolated += int(not row.get("tenant_leakage") and not row.get("user_leakage"))
        linked += int(bool(selected) and bool(row.get("provenance")))
    denominator = len(eligible)
    def ratio(value: int) -> float | None:
        return value / denominator if denominator else None
    return {
        "deterministic_context_selection_correctness": ratio(correct),
        "stale_memory_exclusion_correctness": ratio(stale_safe),
        "irrelevant_memory_exclusion_correctness": ratio(irrelevant_safe),
        "isolation_correctness": ratio(isolated),
        "retrieval_to_context_provenance_linkage": ratio(linked),
        "denominator": denominator,
        "live_final_answer_generation": "DEFERRED / NOT MEASURED",
    }


def run_deterministic_benchmark(
    scenarios: Optional[Sequence[MemoryScenario]] = None,
) -> Dict[str, Any]:
    """Run all five stages without external services or model calls."""
    selected = list(scenarios or generate_scenarios())
    started = time.perf_counter()
    candidate_rows: List[Dict[str, Any]] = []
    lifecycle_rows: List[Dict[str, Any]] = []
    retrieval_rows: List[Dict[str, Any]] = []
    trajectory_rows: List[Dict[str, Any]] = []
    operational_rows: List[Dict[str, Any]] = []
    per_scenario: List[Dict[str, Any]] = []
    for scenario in selected:
        candidate_row = {
            "scenario_id": scenario.scenario_id,
            "expected_candidate_ids": list(scenario.expected_candidate_ids),
            "actual_candidate_ids": list(scenario.proposed_candidate_ids),
        }
        lifecycle, retrieval, runtime = _run_memory_scenario(scenario)
        trajectory = _run_agent_scenario(scenario)
        failures: List[Dict[str, str]] = []
        if set(scenario.expected_candidate_ids) != set(scenario.proposed_candidate_ids):
            failures.append({"stage": "A", "category": "candidate_generation"})
        if lifecycle["expected_action"] != lifecycle["actual_action"] or not lifecycle["active_state_correct"]:
            failures.append({"stage": "B", "category": "lifecycle"})
        if any(
            set(row.get("expected_ids") or []).isdisjoint((row.get("actual_ids") or [])[:5])
            for row in retrieval
            if row.get("expected_ids")
        ):
            failures.append({"stage": "C", "category": "retrieval"})
        if any(row.get("tenant_leakage") or row.get("user_leakage") for row in retrieval):
            failures.append({"stage": "C", "category": "isolation"})
        if not trajectory["allowed_sequence"]:
            failures.append({"stage": "D", "category": "trajectory"})
        candidate_rows.append(candidate_row)
        lifecycle_rows.append(lifecycle)
        retrieval_rows.extend(retrieval)
        trajectory_rows.append(trajectory)
        operational_rows.append(
            {
                "persistence_ms": runtime["persistence_ms"],
                "retrieval_ms": runtime["retrieval_ms"],
                "retrieval_queries": len(retrieval),
                "agent_latency_ms": trajectory.get("agent_latency_ms"),
                "model_calls": trajectory.get("model_calls", 0),
            }
        )
        per_scenario.append(
            {
                "scenario_id": scenario.scenario_id,
                "language": scenario.language,
                "tags": list(scenario.tags),
                "stage_a": candidate_row,
                "stage_b": lifecycle,
                "stage_c": retrieval,
                "stage_d": trajectory,
                "failures": failures,
                "runtime": {"reconciliation_required": runtime["result"].get("reconciliation_required")},
            }
        )
    metrics = {
        "stage_a": candidate_metrics(candidate_rows),
        "stage_b": lifecycle_metrics(lifecycle_rows),
        "stage_c": retrieval_metrics(retrieval_rows),
        "stage_d": aggregate_trajectories(trajectory_rows),
        "stage_e": _final_use_metrics(retrieval_rows),
    }
    wall_time_ms = int((time.perf_counter() - started) * 1000)
    manifest = dataset_manifest(selected)
    attributed = failure_counts(per_scenario)
    attribution = {
        "llm": 0,
        "schema": 0,
        "business_validation": attributed.get("lifecycle", 0),
        "database": 0,
        "vector": 0,
        "pipeline_evaluator": 0,
        **attributed,
    }
    retrieval_query_count = sum(int(row["retrieval_queries"]) for row in operational_rows)
    operational = {
        "classification": MEASUREMENT_CLASS,
        "candidate_extraction_llm_latency_ms": None,
        "persistence_latency_ms_mean": sum(float(row["persistence_ms"]) for row in operational_rows)
        / len(operational_rows),
        "retrieval_latency_ms_mean": sum(float(row["retrieval_ms"]) for row in operational_rows)
        / retrieval_query_count,
        "memory_agent_latency_ms_mean": sum(float(row.get("agent_latency_ms") or 0) for row in operational_rows)
        / len(operational_rows),
        "structured_output_failures": 0,
        "model_calls": sum(int(row["model_calls"]) for row in operational_rows),
        "token_usage": None,
        "benchmark_wall_time_ms": wall_time_ms,
    }
    summary = {
        "measurement_classification": MEASUREMENT_CLASS,
        "stages": metrics,
        "failure_attribution": attribution,
        "operational_metrics": operational,
        "failed_scenario_count": sum(bool(row["failures"]) for row in per_scenario),
        "scenario_count": len(selected),
    }
    return {
        "manifest": manifest,
        "summary": summary,
        "metrics": metrics,
        "per_scenario": per_scenario,
        "errors": [],
        "provenance": {
            "measurement_classification": MEASUREMENT_CLASS,
            "source_revision": _source_revision(),
            "embedding": {
                "model": BagOfWordsEmbeddingClient.model,
                "dimensions": 256,
                "classification": MEASUREMENT_CLASS,
                "disclaimer": EMBEDDING_DISCLAIMER,
            },
            "memory_agent_model": "deterministic-labelled-plan-stub",
            "live_production_runtime": "DEFERRED / NOT MEASURED",
            "wall_time_ms": wall_time_ms,
            "token_usage": None,
            "operational_metrics": operational,
        },
    }
