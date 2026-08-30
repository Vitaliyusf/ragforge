"""CLI entry point for the concurrency baseline.

    py -3.12 scripts/perf/run_baseline.py --gateway-url http://127.0.0.1:8000 \
        --username admin --password ... --requests 100

With no reachable stack it still produces an artifact: every request class is
listed, each unmeasured one carries the reason it could not be driven, and the
run's schema/ladder/config/build are fixed for later comparison. That is the
deliberate degraded mode — `--require-live` turns it into a failure instead,
for CI or for the `CONC-99` campaign where a deferred class is not acceptable.

The harness never invents a number. A class it could not reach is `deferred`;
a percentile the sample count cannot support is `null`; a resource figure the
host cannot measure is `null`. Reading an artifact should never require
knowing which fields the tool tends to make up.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Run as a script (`python scripts/perf/run_baseline.py`) as well as a module.
if __package__ in (None, ""):  # pragma: no cover - import-path shim
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from perf import artifact as artifact_module  # type: ignore[no-redef]
    from perf import drivers, harness, scenarios  # type: ignore[no-redef]
else:
    from . import artifact as artifact_module
    from . import drivers, harness, scenarios


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a CONC-00 concurrency baseline.")
    parser.add_argument("--gateway-url", default=None, help="Base URL of a reachable gateway.")
    parser.add_argument("--username", default=None, help="Gateway login for the measured session.")
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--concurrency",
        default=",".join(str(c) for c in harness.DEFAULT_CONCURRENCY_LADDER),
        help="Comma-separated concurrency ladder.",
    )
    parser.add_argument("--requests", type=int, default=100, help="Measured requests per profile.")
    parser.add_argument("--warmup", type=int, default=10, help="Discarded requests per profile.")
    parser.add_argument(
        "--call-timeout",
        type=float,
        default=harness.DEFAULT_CALL_TIMEOUT_SECONDS,
        help="Per-call ceiling in seconds; an expiry counts as a timeout.",
    )
    parser.add_argument(
        "--include-writes",
        action="store_true",
        help="Also drive classes that create product state (file ingestion).",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Exit non-zero if any request class ends up deferred.",
    )
    parser.add_argument("--label", default="baseline", help="Label in the artifact filename.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=artifact_module.DEFAULT_ARTIFACT_DIR,
        help="Directory the artifact is written to.",
    )
    return parser.parse_args(argv)


def ladder(raw: str) -> List[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values or any(v < 1 for v in values):
        raise ValueError(f"invalid concurrency ladder: {raw!r}")
    return values


def _skip_reason(spec: scenarios.ScenarioSpec, gateway_url: Optional[str], include_writes: bool) -> Optional[str]:
    """Why this class cannot be driven in this invocation, if it cannot."""
    if spec.deferred_reason:
        return spec.deferred_reason
    if spec.mutates_state and not include_writes:
        return (
            "skipped: this class writes product state and --include-writes was "
            "not given, so the baseline stayed re-runnable"
        )
    if spec.target == scenarios.TARGET_GATEWAY and not gateway_url:
        return "no --gateway-url supplied, so no live driver was available"
    if spec.target != scenarios.TARGET_GATEWAY:
        return f"no driver configured for target {spec.target!r} in this invocation"
    if spec.http is None:
        return "no HTTP call declared for this class"
    return None


async def run(args: argparse.Namespace) -> Dict[str, Any]:
    concurrency_ladder = ladder(args.concurrency)
    results: List[Dict[str, Any]] = []
    limitations: List[str] = []

    session: Optional[drivers.GatewaySession] = None
    client_ctx = None
    if args.gateway_url:
        try:
            import httpx
        except ImportError:
            limitations.append(
                "httpx is not installed in this environment, so no live class "
                "could be driven even though a gateway URL was supplied"
            )
        else:
            client_ctx = httpx.AsyncClient(base_url=args.gateway_url, timeout=args.call_timeout)
            session = drivers.GatewaySession(client_ctx)
            if args.username and args.password:
                await session.login(args.username, args.password)
            else:
                limitations.append(
                    "no --username/--password supplied: authenticated classes "
                    "were driven unauthenticated and will report errors"
                )

    try:
        # Every class is listed, always. One that cannot be driven becomes a
        # deferred entry rather than a gap in the artifact.
        for spec in scenarios.SCENARIOS:
            reason = _skip_reason(spec, args.gateway_url, args.include_writes)
            if reason is not None or session is None:
                results.append(
                    artifact_module.scenario_result(
                        spec,
                        deferred_reason=reason
                        or "no authenticated gateway session was established",
                    )
                )
                continue
            profiles = await harness.run_ladder(
                drivers.http_call_fn(session, spec),
                concurrency_ladder=concurrency_ladder,
                requests_per_profile=args.requests,
                warmup_requests=args.warmup,
                call_timeout_seconds=args.call_timeout,
            )
            results.append(artifact_module.scenario_result(spec, profiles=profiles))
    finally:
        if client_ctx is not None:
            await client_ctx.aclose()

    return artifact_module.build_artifact(
        results,
        concurrency_ladder=concurrency_ladder,
        requests_per_profile=args.requests,
        warmup_requests=args.warmup,
        call_timeout_seconds=args.call_timeout,
        extra_limitations=limitations,
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    document = asyncio.run(run(args))
    path = artifact_module.write_artifact(
        document, artifact_module.artifact_path(args.out_dir, args.label)
    )

    measured = [s for s in document["scenarios"] if s["status"] == artifact_module.STATUS_MEASURED]
    deferred = [s for s in document["scenarios"] if s["status"] == artifact_module.STATUS_DEFERRED]
    print(f"baseline written to {path}")
    print(f"measured {len(measured)} request classes, deferred {len(deferred)}")
    for entry in deferred:
        # ASCII only: a Windows console on cp1252 mangles or raises on an
        # em dash, and a baseline run must not die on its own summary line.
        print(f"  deferred: {entry['name']}: {entry['deferred_reason']}")

    if args.require_live and deferred:
        print("--require-live was set and some classes were deferred", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
