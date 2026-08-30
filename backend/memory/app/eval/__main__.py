"""Command-line entry point for local deterministic Memory evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.eval.dataset import generate_scenarios, split_scenarios
from app.eval.export import build_export, export_manifest
from app.eval.runner import run_deterministic_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="full")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    all_scenarios = generate_scenarios()
    scenarios = split_scenarios(all_scenarios, args.split)
    result = run_deterministic_benchmark(scenarios)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = build_export(result, scenarios)
        args.output.write_bytes(payload)
        result["export"] = export_manifest(payload)
        result["export"]["path"] = str(args.output)
    print(json.dumps({"manifest": result["manifest"], "summary": result["summary"], "provenance": result["provenance"], "export": result.get("export")}, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
