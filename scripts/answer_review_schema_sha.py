"""Print the answer-evaluation output-schema fingerprint for deployment.

The benchmark manifest records which JSON Schema the answer-evaluation judge
was held to, so two runs scored under different judge contracts stop comparing
as identical. rag cannot compute that digest: the authoritative model lives in
llm_agent, and rag has no import path to it and no business opening a network
connection from a manifest builder to find out.

So deployment injects it. This script is how the injected value is produced —
by importing the same model ``LLMService`` puts on the invocation and hashing
the same ``model_json_schema()`` call, never by copying a digest from a commit
message or an old ``.env``. A stale hand-written value would keep reporting
"unchanged" through exactly the schema edit the digest exists to catch.

Usage::

    python scripts/answer_review_schema_sha.py
    python scripts/answer_review_schema_sha.py --env

``--env`` prints the assignment line, ready to paste into ``.env`` or to feed
a deployment template::

    ANSWER_EVALUATION_OUTPUT_SCHEMA_SHA256=<64 hex characters>

Re-run it whenever ``AnswerReviewParsedOutput`` changes; if the digest moves
and the manifests do not, benchmarks either side of the change will compare as
"same judge contract" when they were not.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# The two roots the llm_agent container has on its path: `app.*` resolves
# inside the service, `shared.*` beside it.
sys.path[:0] = [
    str(REPO_ROOT / "backend" / "llm_agent"),
    str(REPO_ROOT / "backend"),
]

from app.schemas.llm import answer_review_output_schema_sha256  # noqa: E402

ENV_NAME = "ANSWER_EVALUATION_OUTPUT_SCHEMA_SHA256"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        action="store_true",
        help=f"print as a {ENV_NAME}=<digest> assignment",
    )
    args = parser.parse_args()

    digest = answer_review_output_schema_sha256()
    print(f"{ENV_NAME}={digest}" if args.env else digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
