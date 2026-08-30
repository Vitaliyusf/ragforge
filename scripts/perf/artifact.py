"""The baseline artifact: schema, assembly and writing.

Every `CONC-*` task compares against this document, so its shape is a contract
and not a convenience. It follows the same conventions as
`app.services.benchmark_manifest`: an integer version bumped when the *shape*
changes, unknown values stored as ``None`` rather than guessed, and an
explicit allowlist for configuration so nothing secret travels with a file
people paste into pull requests.

The one rule that shapes the rest: **a class that was not measured appears,
and says why.** A baseline recorded with Docker stopped is still a useful
artifact — it fixes the schema, the ladder, the config and the build — as long
as its unmeasured classes are marked ``deferred`` with a reason instead of
being quietly omitted. Omission is what lets a later reader mistake "we never
measured the reranker" for "the reranker was fine".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .runtime import config_snapshot, hardware_runtime, source_fingerprint, utc_now_iso
from .scenarios import ScenarioSpec

ARTIFACT_KIND = "conc_baseline"

# Bumped when the document's shape changes, so an artifact read back later is
# interpreted under the rules it was written with. Version 1 is the CONC-00
# schema: source/config/hardware/load/scenarios/limitations.
ARTIFACT_SCHEMA_VERSION = 1

STATUS_MEASURED = "measured"
STATUS_DEFERRED = "deferred"

# Where a run lands by default. Kept out of the service trees: this is host
# tooling output, not something an image should ever contain.
DEFAULT_ARTIFACT_DIR = Path("logs") / "perf"


def scenario_result(
    spec: ScenarioSpec,
    profiles: Optional[Sequence[Dict[str, Any]]] = None,
    deferred_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """One scenario's section, measured or deferred.

    A scenario is ``measured`` only when it actually produced profiles. Passing
    an empty profile list without a reason is a bug in the caller, not an empty
    result, so it is rejected rather than written out as a silent gap.
    """
    reason = deferred_reason or spec.deferred_reason
    if profiles:
        return {
            "name": spec.name,
            "status": STATUS_MEASURED,
            "spec": spec.as_dict(),
            "profiles": list(profiles),
            "deferred_reason": None,
        }
    if not reason:
        raise ValueError(
            f"scenario {spec.name!r} produced no profiles and gave no reason; "
            "an unmeasured class must state why it was not measured"
        )
    return {
        "name": spec.name,
        "status": STATUS_DEFERRED,
        "spec": spec.as_dict(),
        "profiles": [],
        "deferred_reason": reason,
    }


def build_artifact(
    scenarios: Sequence[Dict[str, Any]],
    concurrency_ladder: Sequence[int],
    requests_per_profile: int,
    warmup_requests: int,
    call_timeout_seconds: float,
    dataset: Optional[Dict[str, Any]] = None,
    extra_limitations: Iterable[str] = (),
) -> Dict[str, Any]:
    """Assemble a complete baseline document.

    Run-level limitations are the union of what the caller passed and what the
    document can work out for itself — a dirty working tree, and every class
    that ended up deferred. Recomputing them here means a caller cannot forget
    to mention them.
    """
    source = source_fingerprint()
    limitations: List[str] = list(extra_limitations)

    if source.get("dirty"):
        limitations.append(
            "recorded from a working tree with uncommitted changes: the git "
            "SHA alone does not reproduce these numbers"
        )
    if source.get("git_sha") is None:
        limitations.append(
            "no git SHA available in this environment: the source that "
            "produced these numbers is not identified"
        )

    deferred = [s["name"] for s in scenarios if s.get("status") == STATUS_DEFERRED]
    if deferred:
        limitations.append(
            "request classes not measured in this run: " + ", ".join(sorted(deferred))
        )

    return {
        "artifact": ARTIFACT_KIND,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "source": source,
        "config": config_snapshot(),
        "hardware_runtime": hardware_runtime(),
        "load": {
            "concurrency_ladder": list(concurrency_ladder),
            "requests_per_profile": requests_per_profile,
            "warmup_requests": warmup_requests,
            "call_timeout_seconds": call_timeout_seconds,
            "model": "closed-loop: exactly N concurrent callers, not N requests/second",
            "dataset": dataset,
        },
        "scenarios": list(scenarios),
        "limitations": limitations,
    }


def artifact_path(directory: Path = DEFAULT_ARTIFACT_DIR, label: str = "baseline") -> Path:
    """Timestamped path for one run.

    Timestamped rather than overwritten: the whole point of the track is
    comparing runs, and a harness that clobbers the previous file makes the
    second half of that impossible.
    """
    stamp = utc_now_iso().replace(":", "").replace("-", "").split(".")[0]
    return directory / f"conc_{label}_{stamp}.json"


def write_artifact(document: Dict[str, Any], path: Path) -> Path:
    """Write the artifact as indented JSON and return where it landed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path
