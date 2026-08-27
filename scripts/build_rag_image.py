#!/usr/bin/env python3
"""Build the RAG image with truthful Git/source provenance.

The values are passed only to the child ``docker compose build rag`` process;
the script never reads or rewrites ``.env`` and never emits source content or
raw diffs. Use ``--print-only`` to inspect the non-secret stamp without
building.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT_FORMAT = b"ragforge-dirty-source-v1\0"


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _git_text(*args: str) -> str:
    return _git(*args).decode("utf-8", "strict").strip()


def _git_optional_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", "strict").strip()


def _untracked_paths() -> list[Path]:
    raw = _git("ls-files", "--others", "--exclude-standard", "-z")
    names = [name for name in raw.split(b"\0") if name]
    return [ROOT / os.fsdecode(name) for name in sorted(names)]


def dirty_source_fingerprint(git_sha: str) -> str:
    """Hash tracked changes plus non-ignored untracked paths and content."""
    digest = hashlib.sha256(FINGERPRINT_FORMAT)
    digest.update(git_sha.encode("ascii"))
    digest.update(b"\0tracked-diff\0")
    digest.update(_git("diff", "--binary", "--no-ext-diff", "HEAD", "--"))
    digest.update(b"\0untracked\0")
    for path in _untracked_paths():
        relative = path.relative_to(ROOT)
        encoded_path = os.fsencode(str(relative).replace("\\", "/"))
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        if path.is_symlink():
            content = os.fsencode(os.readlink(path))
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b""
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def provenance_stamp(image_tag: str | None = None) -> dict[str, str]:
    git_sha = _git_text("rev-parse", "HEAD")
    branch = _git_optional_text("symbolic-ref", "--short", "-q", "HEAD")
    dirty = bool(_git("status", "--porcelain=v1", "-z", "--untracked-files=all"))
    fingerprint = dirty_source_fingerprint(git_sha) if dirty else ""
    # Match Compose's default so a later `docker compose up` selects the
    # stamped image even though this script deliberately does not persist or
    # rewrite the user's environment. The internal fingerprint, not a mutable
    # local tag, is the authoritative dirty-source identity.
    default_tag = "ragforge-rag:local"
    return {
        "RAGFORGE_GIT_SHA": git_sha,
        "RAGFORGE_GIT_BRANCH": branch,
        "RAGFORGE_GIT_DIRTY": str(dirty).lower(),
        "RAGFORGE_SOURCE_FINGERPRINT_SHA256": fingerprint,
        "RAGFORGE_BUILD_TIMESTAMP": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "RAGFORGE_IMAGE_TAG": image_tag or default_tag,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-tag", help="Exact tag for the built RAG image")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the provenance stamp as JSON without invoking Docker",
    )
    args = parser.parse_args(argv)

    stamp = provenance_stamp(args.image_tag)
    print(json.dumps(stamp, indent=2, sort_keys=True))
    if args.print_only:
        return 0

    environment = os.environ.copy()
    environment.update(stamp)
    subprocess.run(
        ["docker", "compose", "build", "rag"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
