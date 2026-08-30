from __future__ import annotations

from app.eval.dataset import (
    DEFAULT_SCENARIO_COUNT,
    FAMILIES,
    dataset_manifest,
    generate_scenarios,
    split_scenarios,
)


def test_full_dataset_is_large_labelled_synthetic_and_balanced():
    scenarios = generate_scenarios()
    manifest = dataset_manifest(scenarios)

    assert len(scenarios) == DEFAULT_SCENARIO_COUNT >= 500
    assert len({scenario.scenario_id for scenario in scenarios}) == len(scenarios)
    assert manifest["synthetic_only"] is True
    assert manifest["languages"] == {"en": 208, "he": 208, "mixed": 208}
    assert all(any(family in scenario.tags for scenario in scenarios) for family in FAMILIES)
    assert all(scenario.expected_action for scenario in scenarios)
    assert all(scenario.retrieval_queries for scenario in scenarios)


def test_generation_and_hash_are_deterministic():
    first = generate_scenarios()
    second = generate_scenarios()

    assert first == second
    assert dataset_manifest(first) == dataset_manifest(second)
    assert dataset_manifest(first)["dataset_sha256"] == (
        "d0c5f050c4bb9882a30f0ddcafc014a590ff9fcab281b041d6628107c1ba49d4"
    )


def test_stable_splits_and_diagnostic_subsets_preserve_labels():
    scenarios = generate_scenarios()

    assert len(split_scenarios(scenarios, "smoke")) == 40
    assert len(split_scenarios(scenarios, "quick")) == 100
    assert len(split_scenarios(scenarios, "standard")) == 250
    assert len(split_scenarios(scenarios, "full")) == len(scenarios)
    assert split_scenarios(scenarios, "deletion")
    assert split_scenarios(scenarios, "tenant-isolation")
    assert split_scenarios(scenarios, "cross-language")
