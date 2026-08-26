"""Golden Set import parsing and canonical normalization."""
from __future__ import annotations

import json

import pytest

from app.services.golden_set_parser import (
    GoldenSetValidationError,
    parse_golden_set_json,
    parse_golden_set_jsonl,
)


AUTHORING_ITEM = {
    "item_id": "q001",
    "query": " What is the refund window? ",
    "expected_file_names": [" doc.md "],
    "expected_facts": ["Refunds are available for 30 days."],
    "expected_answer": "30 days.",
    "difficulty": "medium",
    "answerable": True,
    "tags": ["factual"],
}


def test_json_authoring_format_normalizes_to_the_canonical_schema():
    items = parse_golden_set_json(json.dumps([AUTHORING_ITEM]))

    assert items == [
        {
            "item_id": "q001",
            "query": "What is the refund window?",
            "relevant_chunk_ids": [],
            "relevant_file_ids": [],
            "expected_file_names": ["doc.md"],
            "expected_answer": "30 days.",
            "expected_claims": ["Refunds are available for 30 days."],
            "difficulty": "medium",
            "answerable": True,
            "tags": ["factual"],
            "notes": None,
        }
    ]


def test_jsonl_existing_eval_format_normalizes_each_line():
    content = "\n".join(
        [
            json.dumps(
                {
                    "item_id": "q001",
                    "query": "First?",
                    "relevant_chunk_ids": ["c1"],
                    "expected_claims": [],
                }
            ),
            "",
            json.dumps(
                {
                    "item_id": "q002",
                    "query": "Second?",
                    "relevant_file_ids": ["f2"],
                }
            ),
        ]
    )

    items = parse_golden_set_jsonl(content)

    assert [item["item_id"] for item in items] == ["q001", "q002"]
    assert items[0]["relevant_file_ids"] == []
    assert items[1]["relevant_chunk_ids"] == []
    assert all(item["expected_file_names"] == [] for item in items)
    assert all(item["answerable"] is None for item in items)


def test_malformed_json_reports_the_source_location():
    with pytest.raises(GoldenSetValidationError, match=r"Malformed JSON at line 1, column"):
        parse_golden_set_json('[{"query":]')


def test_malformed_jsonl_reports_the_physical_line():
    content = '{"item_id":"one","query":"q","relevant_file_ids":["f"]}\n\n{"query":}'
    with pytest.raises(GoldenSetValidationError, match=r"Malformed JSONL at line 3"):
        parse_golden_set_jsonl(content)


def test_malformed_item_reports_its_index_and_field():
    content = json.dumps(
        [
            {"item_id": "ok", "query": "q", "relevant_file_ids": ["f"]},
            {"item_id": "bad", "query": "q", "tags": "not-a-list"},
        ]
    )
    with pytest.raises(GoldenSetValidationError, match=r"Item 1: tags must be a list"):
        parse_golden_set_json(content)


def test_duplicate_item_ids_are_rejected_across_jsonl_lines():
    line = json.dumps(
        {"item_id": "duplicate", "query": "q", "relevant_chunk_ids": ["c"]}
    )
    with pytest.raises(GoldenSetValidationError, match=r"Item 1 repeats item_id 'duplicate'"):
        parse_golden_set_jsonl(f"{line}\n{line}")


def test_source_formats_normalize_identically_when_semantically_equivalent():
    authoring = {
        "item_id": "q001",
        "query": "What is the policy?",
        "expected_facts": ["The policy lasts 30 days."],
        "expected_answer": "30 days.",
        "difficulty": "easy",
        "answerable": True,
        "tags": ["policy"],
    }
    existing = {
        "item_id": "q001",
        "query": "What is the policy?",
        "relevant_chunk_ids": [],
        "relevant_file_ids": [],
        "expected_answer": "30 days.",
        "expected_claims": ["The policy lasts 30 days."],
        "difficulty": "easy",
        "answerable": True,
        "tags": ["policy"],
    }

    assert parse_golden_set_json(json.dumps([authoring])) == parse_golden_set_jsonl(
        json.dumps(existing)
    )


def test_input_size_and_item_count_are_bounded_before_acceptance():
    content = json.dumps([{"query": "q", "relevant_file_ids": ["f"]}])
    with pytest.raises(GoldenSetValidationError, match="input is .* bytes; the limit is 4"):
        parse_golden_set_json(content, max_input_bytes=4)

    lines = "\n".join(
        json.dumps({"item_id": str(index), "query": "q", "relevant_file_ids": ["f"]})
        for index in range(2)
    )
    with pytest.raises(GoldenSetValidationError, match="more than 1 items"):
        parse_golden_set_jsonl(lines, max_items=1)


def test_json_accepts_a_single_item_or_an_items_envelope():
    item = {"item_id": "q1", "query": "q", "relevant_file_ids": ["f"]}
    assert parse_golden_set_json(json.dumps(item)) == parse_golden_set_json(
        json.dumps({"items": [item]})
    )
