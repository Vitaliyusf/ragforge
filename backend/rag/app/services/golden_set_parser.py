"""Parse Golden Set JSON/JSONL files into the eval service's canonical schema."""
from __future__ import annotations

import json
from typing import Any, List, Optional, TypedDict, Union
from uuid import uuid4


DEFAULT_MAX_INPUT_BYTES = 5 * 1024 * 1024


class GoldenSetValidationError(ValueError):
    """A Golden Set input was rejected with a user-actionable reason."""


class CanonicalGoldenSetItem(TypedDict):
    """One normalized item accepted by storage and the eval runner.

    ``expected_facts`` in authoring files is the author-facing spelling of
    the existing eval field ``expected_claims``. Canonical items use the
    latter so current end-to-end scoring remains backward compatible.
    """

    item_id: str
    query: str
    relevant_chunk_ids: List[str]
    relevant_file_ids: List[str]
    expected_file_names: List[str]
    expected_answer: Optional[str]
    expected_claims: List[str]
    difficulty: Optional[str]
    answerable: Optional[bool]
    tags: List[str]
    notes: Optional[str]


RawDataset = Union[str, bytes]


def parse_golden_set(
    content: RawDataset,
    source_format: str,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_items: int = 1000,
    max_query_length: int = 2000,
) -> List[CanonicalGoldenSetItem]:
    """Parse JSON or JSONL and return canonical, validated items."""
    text = _bounded_text(content, max_input_bytes)
    normalized_format = str(source_format or "").strip().lower().lstrip(".")
    if normalized_format == "json":
        raw_items = _parse_json(text)
    elif normalized_format in {"jsonl", "ndjson"}:
        raw_items = _parse_jsonl(text, max_items=max_items)
    else:
        raise GoldenSetValidationError(
            f"Unsupported Golden Set format {source_format!r}; use 'json' or 'jsonl'"
        )
    return normalize_golden_set_items(
        raw_items,
        max_items=max_items,
        max_query_length=max_query_length,
    )


def parse_golden_set_json(
    content: RawDataset,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_items: int = 1000,
    max_query_length: int = 2000,
) -> List[CanonicalGoldenSetItem]:
    """Parse a JSON Golden Set."""
    return parse_golden_set(
        content,
        "json",
        max_input_bytes=max_input_bytes,
        max_items=max_items,
        max_query_length=max_query_length,
    )


def parse_golden_set_jsonl(
    content: RawDataset,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_items: int = 1000,
    max_query_length: int = 2000,
) -> List[CanonicalGoldenSetItem]:
    """Parse a JSON Lines Golden Set."""
    return parse_golden_set(
        content,
        "jsonl",
        max_input_bytes=max_input_bytes,
        max_items=max_items,
        max_query_length=max_query_length,
    )


def normalize_golden_set_items(
    raw_items: Any,
    *,
    max_items: int,
    max_query_length: int,
) -> List[CanonicalGoldenSetItem]:
    """Validate raw items and normalize both supported source styles."""
    if not isinstance(raw_items, list) or not raw_items:
        raise GoldenSetValidationError("A dataset must contain at least one item")
    if len(raw_items) > max_items:
        raise GoldenSetValidationError(
            f"Dataset has {len(raw_items)} items; the limit is {max_items}"
        )

    normalized: List[CanonicalGoldenSetItem] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise GoldenSetValidationError(f"Item {index} is not an object")

        query = raw.get("query")
        if not isinstance(query, str) or not query.strip():
            raise GoldenSetValidationError(f"Item {index} has no query")
        if len(query) > max_query_length:
            raise GoldenSetValidationError(
                f"Item {index} has a {len(query)}-character query; "
                f"the limit is {max_query_length}"
            )

        item_id_value = raw.get("item_id")
        if item_id_value is None:
            item_id = str(uuid4())
        elif not isinstance(item_id_value, str) or not item_id_value.strip():
            raise GoldenSetValidationError(f"Item {index}: item_id must be a non-empty string")
        else:
            item_id = item_id_value.strip()
        if item_id in seen_ids:
            raise GoldenSetValidationError(f"Item {index} repeats item_id {item_id!r}")
        seen_ids.add(item_id)

        chunk_ids = _string_list(raw.get("relevant_chunk_ids"), index, "relevant_chunk_ids")
        file_ids = _string_list(raw.get("relevant_file_ids"), index, "relevant_file_ids")
        file_names = _string_list(raw.get("expected_file_names"), index, "expected_file_names")
        claims = _expected_claims(raw, index)
        tags = _string_list(raw.get("tags"), index, "tags")
        expected_answer = _optional_string(raw.get("expected_answer"), index, "expected_answer")
        difficulty = _optional_string(raw.get("difficulty"), index, "difficulty")
        notes = _optional_string(raw.get("notes"), index, "notes")

        answerable = raw.get("answerable")
        if answerable is not None and not isinstance(answerable, bool):
            raise GoldenSetValidationError(f"Item {index}: answerable must be a boolean or null")

        if not any((chunk_ids, file_ids, file_names, claims, expected_answer)) and answerable is not False:
            raise GoldenSetValidationError(
                f"Item {index} lists no relevant_chunk_ids or relevant_file_ids, "
                "expected_file_names, expected facts, or expected_answer"
            )

        normalized.append(
            {
                "item_id": item_id,
                "query": query.strip(),
                "relevant_chunk_ids": chunk_ids,
                "relevant_file_ids": file_ids,
                "expected_file_names": file_names,
                "expected_answer": expected_answer,
                "expected_claims": claims,
                "difficulty": difficulty,
                "answerable": answerable,
                "tags": tags,
                "notes": notes,
            }
        )
    return normalized


def _bounded_text(content: RawDataset, max_input_bytes: int) -> str:
    if max_input_bytes < 1:
        raise GoldenSetValidationError("The input-size limit must be positive")
    if isinstance(content, bytes):
        size = len(content)
        encoded = content
    elif isinstance(content, str):
        encoded = content.encode("utf-8")
        size = len(encoded)
    else:
        raise GoldenSetValidationError("Golden Set content must be text or UTF-8 bytes")
    if size > max_input_bytes:
        raise GoldenSetValidationError(
            f"Golden Set input is {size} bytes; the limit is {max_input_bytes}"
        )
    try:
        return encoded.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GoldenSetValidationError("Golden Set input must be valid UTF-8") from exc


def _parse_json(text: str) -> List[Any]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GoldenSetValidationError(
            f"Malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if isinstance(document, list):
        return document
    if isinstance(document, dict) and "items" in document:
        items = document["items"]
        if not isinstance(items, list):
            raise GoldenSetValidationError("JSON field 'items' must be an array")
        return items
    if isinstance(document, dict):
        return [document]
    raise GoldenSetValidationError("JSON must contain an item, an item array, or an object with 'items'")


def _parse_jsonl(text: str, *, max_items: int) -> List[Any]:
    items: List[Any] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if len(items) >= max_items:
            raise GoldenSetValidationError(
                f"Dataset has more than {max_items} items; the limit is {max_items}"
            )
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldenSetValidationError(
                f"Malformed JSONL at line {line_number}, column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(item, dict):
            raise GoldenSetValidationError(f"JSONL line {line_number} is not an object")
        items.append(item)
    return items


def _expected_claims(raw: dict[str, Any], index: int) -> List[str]:
    facts = _string_list(raw.get("expected_facts"), index, "expected_facts")
    claims = _string_list(raw.get("expected_claims"), index, "expected_claims")
    if facts and claims and facts != claims:
        raise GoldenSetValidationError(
            f"Item {index}: expected_facts and expected_claims disagree"
        )
    return facts or claims


def _string_list(value: Any, index: int, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GoldenSetValidationError(f"Item {index}: {field} must be a list")
    normalized: List[str] = []
    for element_index, element in enumerate(value):
        if not isinstance(element, str) or not element.strip():
            raise GoldenSetValidationError(
                f"Item {index}: {field}[{element_index}] must be a non-empty string"
            )
        normalized.append(element.strip())
    return normalized


def _optional_string(value: Any, index: int, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GoldenSetValidationError(f"Item {index}: {field} must be a string or null")
    return value.strip() or None
