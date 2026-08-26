"""Parse Golden Set JSON/JSONL files into the eval service's canonical schema."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, TypedDict, Union
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
    unresolved_expected_facts: List[str]
    difficulty: Optional[str]
    answerable: Optional[bool]
    tags: List[str]
    notes: Optional[str]


RawDataset = Union[str, bytes]

UNRESOLVED_FILE = "UNRESOLVED_FILE"
AMBIGUOUS_FILE_MATCH = "AMBIGUOUS_FILE_MATCH"
RESOLVED_FILE = "RESOLVED"
READY = "READY"
UNANSWERABLE = "UNANSWERABLE"
READY_FILE = "READY"
RESOLVED_FACT = "RESOLVED"
UNRESOLVED_FACT = "UNRESOLVED_FACT"


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
    raw_items = _parse_source(text, source_format, max_items=max_items)
    return normalize_golden_set_items(
        raw_items,
        max_items=max_items,
        max_query_length=max_query_length,
    )


def prepare_file_labels(
    items: Sequence[Mapping[str, Any]],
    resolutions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply Files-owned resolutions and classify every valid item."""
    by_label = {
        str(entry.get("label")): entry
        for entry in resolutions
        if isinstance(entry, dict) and entry.get("label")
    }
    counts = {"ready": 0, "unresolved": 0, "ambiguous": 0, "unanswerable": 0}
    errors: List[Dict[str, Any]] = []
    prepared: List[Dict[str, Any]] = []

    for index, source in enumerate(items):
        item: Dict[str, Any] = dict(source)
        if item.get("answerable") is False:
            state = UNANSWERABLE
            counts["unanswerable"] += 1
        else:
            labels = item.get("expected_file_names") or []
            matches = [by_label.get(label, {"status": UNRESOLVED_FILE}) for label in labels]
            ambiguous = [
                label
                for label, match in zip(labels, matches)
                if match.get("status") == AMBIGUOUS_FILE_MATCH
            ]
            unresolved = [
                label
                for label, match in zip(labels, matches)
                if match.get("status") not in {RESOLVED_FILE, AMBIGUOUS_FILE_MATCH}
                or not match.get("file_id")
            ]
            if ambiguous:
                state = AMBIGUOUS_FILE_MATCH
                counts["ambiguous"] += 1
                errors.append(
                    {
                        "item_index": index,
                        "code": AMBIGUOUS_FILE_MATCH,
                        "message": f"Item {index}: ambiguous file match for {', '.join(ambiguous)}",
                    }
                )
            elif unresolved:
                state = UNRESOLVED_FILE
                counts["unresolved"] += 1
                errors.append(
                    {
                        "item_index": index,
                        "code": UNRESOLVED_FILE,
                        "message": f"Item {index}: unresolved file {', '.join(unresolved)}",
                    }
                )
            else:
                state = READY
                counts["ready"] += 1
                resolved_ids = [
                    str(match["file_id"])
                    for match in matches
                    if match.get("file_id")
                ]
                item["relevant_file_ids"] = list(
                    dict.fromkeys([*(item.get("relevant_file_ids") or []), *resolved_ids])
                )
        item["preparation_status"] = state
        prepared.append(item)

    return {
        "items": prepared,
        "counts": counts,
        "errors": errors,
        "blocking": bool(counts["unresolved"] or counts["ambiguous"]),
    }


def prepare_chunk_labels(
    items: Sequence[Mapping[str, Any]],
    resolutions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply deterministic chunk resolutions and classify corpus readiness.

    Automatically resolved chunk IDs are used only when every expected fact
    for an item matched. A partial match falls back to the already-resolved
    file labels so it cannot masquerade as complete chunk-level ground truth.
    """
    by_item = {
        str(entry.get("item_id")): entry
        for entry in resolutions
        if isinstance(entry, dict) and entry.get("item_id")
    }
    counts = {
        "chunk_ready": 0,
        "file_fallback": 0,
        "resolved_facts": 0,
        "unresolved_facts": 0,
        "unready_files": 0,
        "unready_items": 0,
    }
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    prepared: List[Dict[str, Any]] = []

    for index, source in enumerate(items):
        item: Dict[str, Any] = dict(source)
        item["unresolved_expected_facts"] = []
        if item.get("answerable") is False:
            prepared.append(item)
            continue

        facts = list(item.get("expected_claims") or [])
        file_ids = list(item.get("relevant_file_ids") or [])
        resolution = by_item.get(str(item.get("item_id") or ""), {})
        file_states = {
            str(entry.get("file_id")): str(entry.get("status") or "FILE_MISSING")
            for entry in resolution.get("files") or []
            if isinstance(entry, dict) and entry.get("file_id")
        }
        unready = [file_id for file_id in file_ids if file_states.get(file_id) != READY_FILE]
        if unready:
            counts["unready_files"] += len(unready)
            counts["unready_items"] += 1
            for file_id in unready:
                code = file_states.get(file_id, "FILE_MISSING")
                errors.append(
                    {
                        "item_index": index,
                        "code": code,
                        "message": f"Item {index}: file {file_id} is not ready ({code})",
                    }
                )

        fact_entries = {
            str(entry.get("fact")): entry
            for entry in resolution.get("facts") or []
            if isinstance(entry, dict) and entry.get("fact")
        }
        unresolved = [
            fact
            for fact in facts
            if fact_entries.get(fact, {}).get("status") != RESOLVED_FACT
            or not fact_entries.get(fact, {}).get("chunk_ids")
        ]
        counts["resolved_facts"] += len(facts) - len(unresolved)
        counts["unresolved_facts"] += len(unresolved)
        item["unresolved_expected_facts"] = unresolved

        if facts and not unresolved and not unready:
            resolved_ids = list(resolution.get("chunk_ids") or [])
            item["relevant_chunk_ids"] = list(
                dict.fromkeys([*(item.get("relevant_chunk_ids") or []), *resolved_ids])
            )
            counts["chunk_ready"] += 1
        elif facts and file_ids and not unready:
            counts["file_fallback"] += 1
            for fact in unresolved:
                warnings.append(
                    {
                        "item_index": index,
                        "code": UNRESOLVED_FACT,
                        "message": (
                            f"Item {index}: expected fact was not found in a searchable chunk; "
                            "file-level evaluation remains available"
                        ),
                        "fact": fact,
                    }
                )
        elif facts and not file_ids:
            counts["file_fallback"] += 1
            for fact in unresolved:
                warnings.append(
                    {
                        "item_index": index,
                        "code": UNRESOLVED_FACT,
                        "message": f"Item {index}: expected fact has no resolved file scope",
                        "fact": fact,
                    }
                )
        prepared.append(item)

    return {
        "items": prepared,
        "counts": counts,
        "errors": errors,
        "warnings": warnings,
        "blocking": bool(errors),
    }


def validate_golden_set(
    content: RawDataset,
    source_format: str,
    *,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_items: int = 1000,
    max_query_length: int = 2000,
) -> Dict[str, Any]:
    """Validate all independently checkable items without storing a dataset.

    Document-level parse failures have no item index. Once the document can
    be split into items, validation continues after a bad item so an author
    can fix the whole file in one pass instead of discovering one error per
    request.
    """
    try:
        text = _bounded_text(content, max_input_bytes)
        raw_items = _parse_source(text, source_format, max_items=max_items)
    except GoldenSetValidationError as exc:
        return _validation_result(0, 0, 0, [{"item_index": None, "message": str(exc)}])

    total = len(raw_items)
    if not total:
        return _validation_result(
            0,
            0,
            0,
            [{"item_index": None, "message": "A dataset must contain at least one item"}],
        )
    if total > max_items:
        return _validation_result(
            total,
            0,
            total,
            [
                {
                    "item_index": None,
                    "message": f"Dataset has {total} items; the limit is {max_items}",
                }
            ],
        )

    errors: List[Dict[str, Any]] = []
    valid_count = 0
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_items):
        try:
            item = normalize_golden_set_items(
                [raw],
                max_items=1,
                max_query_length=max_query_length,
            )[0]
            item_id = item["item_id"]
            if isinstance(raw, dict) and raw.get("item_id") is not None and item_id in seen_ids:
                raise GoldenSetValidationError(f"Item {index} repeats item_id {item_id!r}")
            seen_ids.add(item_id)
        except GoldenSetValidationError as exc:
            message = str(exc)
            if message.startswith("Item 0"):
                message = f"Item {index}{message[len('Item 0') :]}"
            errors.append({"item_index": index, "message": message})
        else:
            valid_count += 1

    return _validation_result(total, valid_count, total - valid_count, errors)


def _validation_result(
    total_items: int,
    valid_items: int,
    invalid_items: int,
    errors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "valid": not errors,
        "total_items": total_items,
        "valid_items": valid_items,
        "invalid_items": invalid_items,
        "errors": errors,
    }


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
        unresolved_facts = _string_list(
            raw.get("unresolved_expected_facts"), index, "unresolved_expected_facts"
        )
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
                "unresolved_expected_facts": unresolved_facts,
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


def _parse_source(text: str, source_format: str, *, max_items: int) -> List[Any]:
    normalized_format = str(source_format or "").strip().lower().lstrip(".")
    if normalized_format == "json":
        return _parse_json(text)
    if normalized_format in {"jsonl", "ndjson"}:
        return _parse_jsonl(text, max_items=max_items)
    raise GoldenSetValidationError(
        f"Unsupported Golden Set format {source_format!r}; use 'json' or 'jsonl'"
    )


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
