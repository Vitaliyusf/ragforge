from __future__ import annotations

import io
import json
import zipfile

from app.eval.dataset import generate_scenarios
from app.eval.export import build_export, export_manifest
from app.eval.runner import run_deterministic_benchmark


def test_export_is_reproducible_strict_and_contains_authoritative_evidence():
    scenarios = generate_scenarios(52)
    result = run_deterministic_benchmark(scenarios)

    first = build_export(result, scenarios)
    second = build_export(result, scenarios)

    assert first == second
    assert export_manifest(first) == export_manifest(second)
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert set(archive.namelist()) == {
            "dataset.json",
            "errors.json",
            "manifest.json",
            "metrics.json",
            "per-scenario.json",
            "provenance.json",
            "summary.json",
        }
        for name in archive.namelist():
            json.loads(
                archive.read(name),
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )


def test_export_contains_only_synthetic_dataset_rows():
    scenarios = generate_scenarios(26)
    payload = build_export(run_deterministic_benchmark(scenarios), scenarios)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        dataset = json.loads(archive.read("dataset.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert len(dataset) == 26
    assert manifest["synthetic_only"] is True
