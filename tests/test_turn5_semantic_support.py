"""Regression tests for Turn-5 bounded source-span semantic support."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from semantic_support import (
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
    evaluate_observed_claims,
    evaluate_source_span_support,
)

ROOT = Path(__file__).resolve().parents[1]


def load_benchmark_runner():
    path = ROOT / "scripts" / "run_turn5_semantic_benchmark.py"
    spec = importlib.util.spec_from_file_location("run_turn5_semantic_benchmark", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_implementation_phrase_entails() -> None:
    span = (
        'subprocess.run(["git", "rev-parse", "--verify", '
        '"HEAD^{commit}"], shell=False)'
    )

    result = evaluate_source_span_support(
        "git rev-parse --verify HEAD^{commit}",
        span,
        "S1#E1",
    )

    assert result.relation == SOURCE_ENTAILS_CLAIM
    assert result.unsupported_numbers == ()
    assert result.unsupported_identifiers == ()


def test_new_numeric_precision_forces_insufficient() -> None:
    span = "pytest collection runs before the declared test command"

    result = evaluate_source_span_support(
        "The collection contains 47 artifacts.",
        span,
        "S1#E2",
    )

    assert result.relation == SOURCE_INSUFFICIENT
    assert "47" in result.unsupported_numbers


def test_semantic_expansion_forces_insufficient() -> None:
    span = "resolve_commit_sha returns the exact checked-out Git commit"

    result = evaluate_source_span_support(
        "The commit identity mechanism is complete and production ready.",
        span,
        "S1#E1",
    )

    assert result.relation == SOURCE_INSUFFICIENT
    assert "semantic-expansion" in result.reason or result.token_coverage < 0.92


def test_explicit_negation_conflict_contradicts() -> None:
    span = "verification status is not FAILED for this accepted receipt"

    result = evaluate_source_span_support(
        "verification status is FAILED for this accepted receipt",
        span,
        "T1#E1",
    )

    assert result.relation == SOURCE_CONTRADICTS_CLAIM


def test_observed_claim_batch_requires_every_claim_to_entail() -> None:
    response = """
OBSERVED[S1#E1]: git rev-parse --verify HEAD^{commit}
OBSERVED[S1#E2]: The collection contains 47 artifacts.
INFERENCE: The second observation should be quarantined.
"""
    spans = {
        "S1#E1": "git rev-parse --verify HEAD^{commit}",
        "S1#E2": "pytest collection runs before execution",
    }

    result = evaluate_observed_claims(response, spans)

    assert result["semantic_gate_pass"] is False
    assert result["relation_counts"][SOURCE_ENTAILS_CLAIM] == 1
    assert result["relation_counts"][SOURCE_INSUFFICIENT] == 1


def test_missing_span_text_abstains_instead_of_guessing() -> None:
    response = "OBSERVED[S9#E9]: A precise claim without supplied span text."

    result = evaluate_observed_claims(response, {})

    assert result["semantic_gate_pass"] is False
    assert result["missing_pointer_count"] == 1
    assert result["relation_counts"][SOURCE_INSUFFICIENT] == 1


def test_turn5_source_reviewed_benchmark_matches_every_label() -> None:
    runner = load_benchmark_runner()
    receipt = runner.run_benchmark(ROOT / "benchmarks" / "turn5_semantic_support.json")

    assert receipt["status"] == "PASS"
    assert receipt["case_count"] == 10
    assert receipt["correct_count"] == 10
    assert receipt["exact_match_rate"] == 1.0
