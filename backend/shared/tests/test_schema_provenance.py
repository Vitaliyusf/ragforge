"""Tests for deterministic JSON Schema fingerprinting.

The digest is only useful if two processes agree on it, so what is defended
here is determinism against the things that legitimately vary between two
constructions of the same schema — key order, incidental whitespace — and
sensitivity to the things that must not be lost, down to a single constraint.
"""
import hashlib
import json
import unittest

from shared.schema_provenance import canonical_schema_json, canonical_schema_sha256

SCHEMA = {
    "title": "AnswerReview",
    "type": "object",
    "properties": {
        "claims": {"type": "array", "maxItems": 4},
        "issues": {"type": "array"},
    },
}


class CanonicalSchemaJsonTests(unittest.TestCase):
    def test_keys_are_sorted_and_separators_are_compact(self):
        self.assertEqual(
            canonical_schema_json({"b": 1, "a": 2}),
            b'{"a":2,"b":1}',
        )

    def test_non_ascii_is_encoded_as_utf8_not_escaped(self):
        self.assertEqual(
            canonical_schema_json({"description": "café"}),
            '{"description":"café"}'.encode("utf-8"),
        )


class CanonicalSchemaSha256Tests(unittest.TestCase):
    def test_digest_matches_sha256_of_the_canonical_bytes(self):
        self.assertEqual(
            canonical_schema_sha256(SCHEMA),
            hashlib.sha256(canonical_schema_json(SCHEMA)).hexdigest(),
        )

    def test_same_schema_hashes_the_same(self):
        self.assertEqual(canonical_schema_sha256(SCHEMA), canonical_schema_sha256(SCHEMA))

    def test_key_order_does_not_change_the_digest(self):
        reordered = json.loads(json.dumps(SCHEMA))
        reordered["properties"] = {
            "issues": SCHEMA["properties"]["issues"],
            "claims": SCHEMA["properties"]["claims"],
        }
        self.assertEqual(
            canonical_schema_sha256(SCHEMA),
            canonical_schema_sha256(reordered),
        )

    def test_changing_max_items_changes_the_digest(self):
        loosened = json.loads(json.dumps(SCHEMA))
        loosened["properties"]["claims"]["maxItems"] = 8
        self.assertNotEqual(
            canonical_schema_sha256(SCHEMA),
            canonical_schema_sha256(loosened),
        )

    def test_removing_a_constraint_changes_the_digest(self):
        unbounded = json.loads(json.dumps(SCHEMA))
        del unbounded["properties"]["claims"]["maxItems"]
        self.assertNotEqual(
            canonical_schema_sha256(SCHEMA),
            canonical_schema_sha256(unbounded),
        )


if __name__ == "__main__":
    unittest.main()
