"""Dataset import preparation: filename and fact resolution before storage."""
from __future__ import annotations

import asyncio
import json


from app.services.eval_runner import (
    EvalRunner,
)
from app.services.eval_store import EvalStore
from shared.context import bound_context

from app.tests.eval._harness import (
    ADMIN,
    FakeBackend,
    build_config,
)

def test_import_preparation_resolves_filenames_before_storage():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[
            {"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}
        ]
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps([{"query": "Where?", "expected_file_names": ["Guide.pdf"]}])

    async def _go():
        validation = await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )
        imported = await runner.handle(
            "create_eval_dataset",
            {"name": "Prepared", "content": content, "format": "json"},
        )
        return validation, imported

    with bound_context(**ADMIN.to_dict()):
        validation, imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    assert validation["preparation"] == {
        "ready": 1,
        "unresolved": 0,
        "ambiguous": 0,
        "unanswerable": 0,
        "chunk_ready": 0,
        "file_fallback": 0,
        "resolved_facts": 0,
        "unresolved_facts": 0,
        "unready_files": 0,
        "unready_items": 0,
        "blocking": False,
        "warnings": [],
    }
    assert dataset["items"][0]["relevant_file_ids"] == ["file-1"]


def test_import_preparation_blocks_missing_and_ambiguous_filenames_with_codes():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[
            {"label": "missing.pdf", "status": "UNRESOLVED_FILE", "file_id": None},
            {"label": "copy.pdf", "status": "AMBIGUOUS_FILE_MATCH", "file_id": None},
        ]
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {"query": "Missing?", "expected_file_names": ["missing.pdf"]},
            {"query": "Which copy?", "expected_file_names": ["copy.pdf"]},
        ]
    )

    async def _go():
        return await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )

    with bound_context(**ADMIN.to_dict()):
        result = asyncio.run(_go())

    assert result["validation"]["valid"] is False
    assert result["preparation"]["unresolved"] == 1
    assert result["preparation"]["ambiguous"] == 1
    assert [error["code"] for error in result["validation"]["errors"]] == [
        "UNRESOLVED_FILE",
        "AMBIGUOUS_FILE_MATCH",
    ]


def test_import_preparation_resolves_exact_facts_to_all_matching_chunks():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [{"file_id": "file-1", "status": "READY", "searchable": True}],
                "facts": [
                    {
                        "fact": "Refunds are available for 30 days.",
                        "status": "RESOLVED",
                        "chunk_ids": ["c1", "c2"],
                    }
                ],
                "chunk_ids": ["c1", "c2"],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {
                "item_id": "q1",
                "query": "Refund window?",
                "expected_file_names": ["Guide.pdf"],
                "expected_facts": ["Refunds are available for 30 days."],
            }
        ]
    )

    async def _go():
        return await runner.handle(
            "create_eval_dataset",
            {"name": "Prepared", "content": content, "format": "json"},
        )

    with bound_context(**ADMIN.to_dict()):
        imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    item = dataset["items"][0]
    assert item["relevant_file_ids"] == ["file-1"]
    assert item["relevant_chunk_ids"] == ["c1", "c2"]
    assert item["unresolved_expected_facts"] == []
    assert imported["preparation"]["chunk_ready"] == 1
    assert imported["preparation"]["resolved_facts"] == 1


def test_unresolved_fact_is_explicit_and_keeps_file_level_eval_usable():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    fact = "Refunds are available for 30 days."
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [{"file_id": "file-1", "status": "READY", "searchable": True}],
                "facts": [{"fact": fact, "status": "UNRESOLVED_FACT", "chunk_ids": []}],
                "chunk_ids": [],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [
            {
                "item_id": "q1",
                "query": "Refund window?",
                "expected_file_names": ["Guide.pdf"],
                "expected_facts": [fact],
            }
        ]
    )

    async def _go():
        return await runner.handle(
            "create_eval_dataset",
            {"name": "Fallback", "content": content, "format": "json"},
        )

    with bound_context(**ADMIN.to_dict()):
        imported = asyncio.run(_go())
        dataset = store.get_dataset(imported["dataset"]["dataset_id"])

    item = dataset["items"][0]
    assert item["relevant_chunk_ids"] == []
    assert item["relevant_file_ids"] == ["file-1"]
    assert item["unresolved_expected_facts"] == [fact]
    assert imported["preparation"]["blocking"] is False
    assert imported["preparation"]["file_fallback"] == 1
    assert imported["preparation"]["warnings"][0]["code"] == "UNRESOLVED_FACT"


def test_unsearchable_file_blocks_import_readiness():
    config = build_config()
    store = EvalStore(config)  # type: ignore[arg-type]
    backend = FakeBackend(
        resolutions=[{"label": "Guide.pdf", "status": "RESOLVED", "file_id": "file-1"}],
        chunk_resolutions=[
            {
                "item_id": "q1",
                "files": [
                    {
                        "file_id": "file-1",
                        "status": "FILE_NOT_SEARCHABLE",
                        "searchable": False,
                    }
                ],
                "facts": [],
                "chunk_ids": [],
            }
        ],
    )
    runner = EvalRunner(config, store, backend)  # type: ignore[arg-type]
    content = json.dumps(
        [{"item_id": "q1", "query": "Where?", "expected_file_names": ["Guide.pdf"]}]
    )

    async def _go():
        return await runner.handle(
            "validate_eval_dataset", {"content": content, "format": "json"}
        )

    with bound_context(**ADMIN.to_dict()):
        result = asyncio.run(_go())

    assert result["validation"]["valid"] is False
    assert result["preparation"]["blocking"] is True
    assert result["preparation"]["unready_files"] == 1
    assert result["validation"]["errors"][0]["code"] == "FILE_NOT_SEARCHABLE"


# ── Concurrency ───────────────────────────────────────────────────────────


