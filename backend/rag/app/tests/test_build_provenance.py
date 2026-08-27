"""Focused tests for deterministic dirty-source build provenance."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "build_rag_image", ROOT / "scripts" / "build_rag_image.py"
)
assert SPEC is not None and SPEC.loader is not None
build_rag_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_rag_image)


def test_dirty_source_fingerprint_is_deterministic_and_content_sensitive(
    tmp_path, monkeypatch
):
    untracked = tmp_path / "new.py"
    untracked.write_text("first\n", encoding="utf-8")
    monkeypatch.setattr(build_rag_image, "ROOT", tmp_path)
    monkeypatch.setattr(build_rag_image, "_untracked_paths", lambda: [untracked])
    monkeypatch.setattr(
        build_rag_image,
        "_git",
        lambda *args: b"tracked patch" if args[0] == "diff" else b"",
    )

    first = build_rag_image.dirty_source_fingerprint("a" * 40)
    assert build_rag_image.dirty_source_fingerprint("a" * 40) == first

    untracked.write_text("second\n", encoding="utf-8")
    assert build_rag_image.dirty_source_fingerprint("a" * 40) != first


@pytest.mark.parametrize("dirty", [False, True])
def test_provenance_stamp_records_dirty_state_and_only_hashes_dirty_trees(
    monkeypatch, dirty
):
    def fake_git(*args):
        if args[0] == "rev-parse":
            return b"1" * 40 + b"\n"
        if args[0] == "status":
            return b" M backend/rag/app/main.py\0" if dirty else b""
        raise AssertionError(args)

    monkeypatch.setattr(build_rag_image, "_git", fake_git)
    monkeypatch.setattr(build_rag_image, "_git_optional_text", lambda *args: "main")
    monkeypatch.setattr(
        build_rag_image,
        "dirty_source_fingerprint",
        lambda git_sha: "f" * 64,
    )

    stamp = build_rag_image.provenance_stamp()

    assert stamp["RAGFORGE_GIT_DIRTY"] == str(dirty).lower()
    expected_fingerprint = "f" * 64 if dirty else ""
    assert stamp["RAGFORGE_SOURCE_FINGERPRINT_SHA256"] == expected_fingerprint
    assert stamp["RAGFORGE_IMAGE_TAG"] == "ragforge-rag:local"
