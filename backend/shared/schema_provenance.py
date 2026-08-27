"""Deterministic fingerprints for structured-output JSON Schemas.

A benchmark that pins its model, its retrieval settings and its token budgets
still cannot say *which* output contract the judge was held to. Two runs whose
manifests differ only by ``captured_at`` may have been scored under different
schemas — a bounded ``claims`` array against an unbounded one, say — and a
reader comparing their quality metrics would be comparing two different
measurements.

This module turns a JSON Schema into one 64-character fact that a manifest can
carry and a comparison can diff. The canonicalization is deliberately boring
and fully specified, because the hash is only useful if two processes on two
machines agree on it:

* ``sort_keys=True`` — schema dicts are built by Pydantic in construction
  order, which is not a contract;
* ``separators=(",", ":")`` — no incidental whitespace;
* ``ensure_ascii=False`` plus an explicit UTF-8 encode — a non-ASCII
  description hashes as the characters it is, not as an escape sequence;
* SHA-256 over those bytes.

It lives in ``shared`` so that a service computing the hash and a service
recording it cannot drift into two different canonicalizations of the same
schema.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

__all__ = ["canonical_schema_json", "canonical_schema_sha256"]


def canonical_schema_json(schema: Mapping[str, Any]) -> bytes:
    """Return ``schema`` as deterministic UTF-8 JSON bytes."""
    return json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_schema_sha256(schema: Mapping[str, Any]) -> str:
    """Return the SHA-256 hex digest of ``schema``'s canonical JSON form.

    Equal schemas hash equally regardless of key order; any change to the
    schema — including a constraint as small as ``maxItems`` — changes the
    digest.
    """
    return hashlib.sha256(canonical_schema_json(schema)).hexdigest()
