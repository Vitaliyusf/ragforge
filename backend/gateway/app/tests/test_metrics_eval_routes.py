"""Tests for the eval-harness routes on the admin metrics router.

Doubles sit at the RabbitMQ boundary and the real ``MetricsService`` runs
between, so the tests cover the thing that can actually be wrong here: the
action each route sends, the admin gate, and — the point of the whole
validation story — that a malformed upload is refused with a reason rather
than truncated into a dataset that produces confident, wrong recall numbers.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.deps import get_metrics_service
from app.rest.v1 import metrics as metrics_routes
from app.services.metrics_service import MetricsService
from shared.auth import AuthIdentity

TENANT = "tenant-a"

DATASET = {
    "dataset_id": "d-1",
    "tenant_id": TENANT,
    "name": "Support golden set",
    "items": [{"item_id": "i-1", "query": "q", "relevant_chunk_ids": ["c1"]}],
}

RUN = {
    "run_id": "r-1",
    "dataset_id": "d-1",
    "status": "running",
    "config_snapshot": {"top_k_documents": 6, "unobserved": ["embedding_model"]},
    "results": {},
    "per_item": [],
}

VALID_ITEM = {"query": "What is the refund window?", "relevant_chunk_ids": ["c1"]}


class DummyRPCClient:
    """Answer eval actions from a table, recording every payload sent."""

    def __init__(self, override: Optional[Dict[str, Any]] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.override = override

    async def send_request(self, routing_key, payload, timeout=None):
        self.calls.append({"routing_key": routing_key, "payload": payload})
        if self.override is not None:
            return self.override
        # A str-Enum's str() is "RagAction.MEMBER", not its value; dict
        # lookup works on the member itself because it hashes as its value.
        action = payload.get("action")
        return {
            "list_eval_datasets": {"datasets": [{"dataset_id": "d-1", "item_count": 1}]},
            "create_eval_dataset": {"dataset": DATASET},
            "update_eval_dataset": {"dataset": {**DATASET, "name": "Renamed"}},
            "delete_eval_dataset": {"dataset_id": "d-1", "deleted": True},
            "start_eval_run": {"run": RUN},
            "list_eval_runs": {"runs": [{**RUN, "per_item": []}]},
            "get_eval_run": {"run": {**RUN, "per_item": [{"item_id": "i-1"}]}},
        }.get(action, {})


class DummyPrometheus:
    """Never consulted by the eval routes; present so the service can be built."""

    async def query(self, expr: str):
        return []

    async def query_range(self, expr, start, end, step):
        return []

    async def is_available(self) -> bool:
        return True


class DummyLogger:
    def log(self, *args, **kwargs) -> None:
        return None


def build_service(override: Optional[Dict[str, Any]] = None) -> MetricsService:
    config = SimpleNamespace(
        request_topics={"rag": "rag", "files": "files"},
        short_timeout=5.0,
        default_timeout=30.0,
    )
    return MetricsService(DummyRPCClient(override), DummyLogger(), config, DummyPrometheus())


def build_app(service, *, role: str = "admin") -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_routes.router, prefix="/v1")
    app.dependency_overrides[get_metrics_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: AuthIdentity(
        tenant_id=TENANT,
        user_id="admin-a" if role == "admin" else "user-a",
        role=role,
        admin_id="admin-a",
    )
    return app


def last_payload(service) -> Dict[str, Any]:
    return service.rpc_client.calls[-1]["payload"]


# ── The seven routes ──────────────────────────────────────────────────────

def test_listing_datasets_sends_the_list_action():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.get("/v1/metrics/eval/datasets")

    assert response.status_code == 200
    assert response.json()["datasets"][0]["dataset_id"] == "d-1"
    assert last_payload(service)["action"] == "list_eval_datasets"


def test_creating_a_dataset_forwards_normalized_items():
    service = build_service()
    body = {"name": "Support", "description": "a set", "items": [VALID_ITEM]}
    with TestClient(build_app(service)) as client:
        response = client.post("/v1/metrics/eval/datasets", json=body)

    assert response.status_code == 200
    assert response.json()["dataset"]["dataset_id"] == "d-1"
    payload = last_payload(service)
    assert payload["action"] == "create_eval_dataset"
    assert payload["name"] == "Support"
    # The absent id field is filled in as an empty list, not dropped, so rag
    # never has to guess whether it was omitted or empty.
    assert payload["items"][0]["relevant_file_ids"] == []
    assert payload["items"][0]["item_id"] is None


def test_updating_a_dataset_forwards_only_what_was_sent():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.patch("/v1/metrics/eval/datasets/d-1", json={"name": "Renamed"})

    assert response.status_code == 200
    payload = last_payload(service)
    assert payload["action"] == "update_eval_dataset"
    assert payload["dataset_id"] == "d-1"
    assert payload["name"] == "Renamed"
    # None, not []: an omitted items field must not wipe the dataset.
    assert payload["items"] is None


def test_deleting_a_dataset_sends_the_delete_action():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.delete("/v1/metrics/eval/datasets/d-1")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert last_payload(service)["action"] == "delete_eval_dataset"


def test_starting_a_run_returns_the_run_id_immediately():
    """The route must not wait for the run: that is the whole design."""
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post("/v1/metrics/eval/runs", json={"dataset_id": "d-1"})

    assert response.status_code == 200
    body = response.json()["run"]
    assert body["run_id"] == "r-1"
    assert body["status"] == "running"
    assert last_payload(service)["action"] == "start_eval_run"


def test_run_history_forwards_the_dataset_filter_and_limit():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.get("/v1/metrics/eval/runs?dataset_id=d-1&limit=5")

    assert response.status_code == 200
    payload = last_payload(service)
    assert payload["action"] == "list_eval_runs"
    assert payload["dataset_id"] == "d-1"
    assert payload["limit"] == 5


def test_one_run_carries_its_per_item_rows():
    """The listing omits them; the single-run route is where they live."""
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.get("/v1/metrics/eval/runs/r-1")

    assert response.status_code == 200
    assert response.json()["run"]["per_item"] == [{"item_id": "i-1"}]
    assert last_payload(service)["action"] == "get_eval_run"


def test_the_run_carries_the_config_snapshot_for_comparison():
    service = build_service()
    with TestClient(build_app(service)) as client:
        snapshot = client.get("/v1/metrics/eval/runs/r-1").json()["run"]["config_snapshot"]

    assert snapshot["top_k_documents"] == 6
    assert snapshot["unobserved"] == ["embedding_model"]


# ── Admin gating ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/v1/metrics/eval/datasets", None),
        ("post", "/v1/metrics/eval/datasets", {"name": "A", "items": [VALID_ITEM]}),
        ("patch", "/v1/metrics/eval/datasets/d-1", {"name": "B"}),
        ("delete", "/v1/metrics/eval/datasets/d-1", None),
        ("post", "/v1/metrics/eval/runs", {"dataset_id": "d-1"}),
        ("get", "/v1/metrics/eval/runs", None),
        ("get", "/v1/metrics/eval/runs/r-1", None),
    ],
)
def test_regular_users_are_forbidden_on_every_eval_route(method, path, body):
    """The golden set spans every user in the tenant, so it is admin-only."""
    service = build_service()
    app = build_app(service, role="user")

    with TestClient(app) as client:
        response = getattr(client, method)(path, **({"json": body} if body else {}))

    assert response.status_code == 403
    # Refused before any RPC: a forbidden request must not reach rag at all.
    assert service.rpc_client.calls == []


# ── Upload validation ─────────────────────────────────────────────────────

def test_an_oversized_dataset_is_rejected_before_any_rpc():
    """Rejected, not truncated — and without costing a round-trip."""
    service = build_service()
    items = [{"query": f"q{i}", "relevant_chunk_ids": ["c"]} for i in range(1001)]

    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/datasets", json={"name": "Big", "items": items}
        )

    assert response.status_code == 422
    assert service.rpc_client.calls == []


def test_an_item_without_ground_truth_is_rejected():
    """An unscoreable item would silently inflate items_skipped forever."""
    service = build_service()
    body = {"name": "A", "items": [{"query": "no labels"}]}

    with TestClient(build_app(service)) as client:
        response = client.post("/v1/metrics/eval/datasets", json=body)

    assert response.status_code == 422
    assert service.rpc_client.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "items": [VALID_ITEM]},
        {"name": "A", "items": []},
        {"name": "A", "items": [{"query": "x" * 2001, "relevant_chunk_ids": ["c"]}]},
        {"name": "A"},
    ],
)
def test_malformed_uploads_are_rejected(body):
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post("/v1/metrics/eval/datasets", json=body)

    assert response.status_code == 422
    assert service.rpc_client.calls == []


def test_a_run_defaults_to_the_free_retrieval_mode():
    """Saying nothing must not start the run that spends tokens."""
    service = build_service()
    with TestClient(build_app(service)) as client:
        client.post("/v1/metrics/eval/runs", json={"dataset_id": "d-1"})

    assert last_payload(service)["mode"] == "retrieval"


def test_an_end_to_end_run_forwards_its_mode():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/runs", json={"dataset_id": "d-1", "mode": "end_to_end"}
        )

    assert response.status_code == 200
    assert last_payload(service)["mode"] == "end_to_end"


def test_an_unknown_run_mode_is_refused_before_it_costs_an_rpc():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/runs", json={"dataset_id": "d-1", "mode": "cheap"}
        )

    assert response.status_code == 422
    assert service.rpc_client.calls == []


def test_a_retrieval_estimate_is_zero_because_no_model_is_called():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/runs/estimate", json={"item_count": 200, "mode": "retrieval"}
        )

    body = response.json()
    assert response.status_code == 200
    assert body["calls_per_item"] == 0
    assert body["estimated_cost_usd"] == 0.0
    # Pure arithmetic in the gateway: estimating must not touch rag.
    assert service.rpc_client.calls == []


def test_an_end_to_end_estimate_reports_tokens_and_whether_the_model_is_priced():
    service = build_service()
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/runs/estimate",
            json={"item_count": 20, "mode": "end_to_end", "model": "not-a-priced-model"},
        )

    body = response.json()
    assert body["calls_per_item"] == 2
    assert body["estimated_tokens_in"] > 0
    # A $0.00 estimate here means "unpriced", and the flag is what says so.
    assert body["model_priced"] is False


def test_starting_a_run_needs_a_dataset_id():
    service = build_service()
    with TestClient(build_app(service)) as client:
        assert client.post("/v1/metrics/eval/runs", json={"dataset_id": ""}).status_code == 422


# ── Downstream refusals keep their reason ─────────────────────────────────

def test_a_validation_refusal_from_rag_becomes_a_400_naming_the_item():
    """The shared error envelope would flatten this into a reasonless 500."""
    service = build_service(
        {"eval_error": {"kind": "validation", "message": "Item 3 has no query"}}
    )
    with TestClient(build_app(service)) as client:
        response = client.post(
            "/v1/metrics/eval/datasets", json={"name": "A", "items": [VALID_ITEM]}
        )

    assert response.status_code == 400
    assert "Item 3 has no query" in response.json()["detail"]


def test_an_unknown_dataset_becomes_a_404():
    service = build_service(
        {"eval_error": {"kind": "not_found", "message": "No eval dataset 'nope'"}}
    )
    with TestClient(build_app(service)) as client:
        response = client.get("/v1/metrics/eval/runs/r-1")

    assert response.status_code == 404


def test_a_cross_tenant_refusal_becomes_a_403():
    service = build_service(
        {"eval_error": {"kind": "forbidden", "message": "Administrator role required"}}
    )
    with TestClient(build_app(service)) as client:
        response = client.get("/v1/metrics/eval/datasets")

    assert response.status_code == 403
