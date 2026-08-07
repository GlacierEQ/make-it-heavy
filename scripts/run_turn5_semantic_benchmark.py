#!/usr/bin/env python3
"""Run the bounded source-span semantic support benchmark fail-closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from semantic_support import (  # noqa: E402
    SEMANTIC_RELATIONS,
    evaluate_source_span_support,
    sha256_text,
)

DEFAULT_BENCHMARK = ROOT / "benchmarks" / "turn5_semantic_support.json"


class BenchmarkValidationError(ValueError):
    """Raised when benchmark evidence is missing or structurally invalid."""


def _require_string(mapping: Mapping[str, object], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkValidationError(f"{context}.{key} must be a non-empty string")
    return value


def load_benchmark(path: Path) -> Tuple[Dict[str, object], str]:
    """Read and validate one benchmark exactly once."""

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BenchmarkValidationError(f"benchmark read failed: {exc}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BenchmarkValidationError(f"benchmark JSON is malformed: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchmarkValidationError("benchmark root must be an object")

    for key in ("schema", "source_repository", "source_commit", "truth_boundary"):
        _require_string(payload, key, "benchmark")

    source_spans = payload.get("source_spans")
    if not isinstance(source_spans, dict) or not source_spans:
        raise BenchmarkValidationError("benchmark.source_spans must be a non-empty object")
    for pointer, span_text in source_spans.items():
        if not isinstance(pointer, str) or not pointer.strip():
            raise BenchmarkValidationError("source span pointer must be a non-empty string")
        if not isinstance(span_text, str) or not span_text.strip():
            raise BenchmarkValidationError(f"source span {pointer!r} must contain text")

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkValidationError("benchmark.cases must be a non-empty array")
    seen_ids = set()
    for index, raw_case in enumerate(cases):
        context = f"benchmark.cases[{index}]"
        if not isinstance(raw_case, dict):
            raise BenchmarkValidationError(f"{context} must be an object")
        case_id = _require_string(raw_case, "id", context)
        if case_id in seen_ids:
            raise BenchmarkValidationError(f"duplicate benchmark case id: {case_id}")
        seen_ids.add(case_id)
        pointer = _require_string(raw_case, "pointer", context)
        _require_string(raw_case, "claim", context)
        expected = _require_string(raw_case, "expected", context)
        _require_string(raw_case, "origin", context)
        if pointer not in source_spans:
            raise BenchmarkValidationError(
                f"{context}.pointer does not exist in source_spans: {pointer}"
            )
        if expected not in SEMANTIC_RELATIONS:
            raise BenchmarkValidationError(
                f"{context}.expected is not a semantic relation: {expected}"
            )

    minimum_accuracy = payload.get("minimum_accuracy", 1.0)
    if not isinstance(minimum_accuracy, (int, float)) or isinstance(minimum_accuracy, bool):
        raise BenchmarkValidationError("benchmark.minimum_accuracy must be numeric")
    if not 0.0 <= float(minimum_accuracy) <= 1.0:
        raise BenchmarkValidationError("benchmark.minimum_accuracy must be between 0 and 1")
    payload["minimum_accuracy"] = float(minimum_accuracy)
    return payload, raw_text


def run_benchmark(path: Path) -> Dict[str, object]:
    payload, raw_text = load_benchmark(path)
    spans = payload["source_spans"]
    assert isinstance(spans, dict)
    cases = payload["cases"]
    assert isinstance(cases, list)

    rows: List[Dict[str, object]] = []
    correct = 0
    for case in cases:
        assert isinstance(case, dict)
        pointer = str(case["pointer"])
        span_text = str(spans[pointer])
        result = evaluate_source_span_support(
            str(case["claim"]),
            span_text,
            pointer,
        )
        passed = result.relation == case["expected"]
        correct += int(passed)
        rows.append(
            {
                "id": case["id"],
                "pointer": pointer,
                "expected": case["expected"],
                "actual": result.relation,
                "pass": passed,
                "reason": result.reason,
                "claim_sha256": result.claim_sha256,
                "span_sha256": result.span_sha256,
                "token_coverage": result.token_coverage,
                "unsupported_numbers": list(result.unsupported_numbers),
                "unsupported_identifiers": list(result.unsupported_identifiers),
                "unsupported_dates": list(result.unsupported_dates),
                "origin": case["origin"],
            }
        )

    case_count = len(rows)
    exact_match_rate = round(correct / case_count, 4) if case_count else 0.0
    minimum_accuracy = float(payload["minimum_accuracy"])
    status = "PASS" if exact_match_rate >= minimum_accuracy else "FAIL"
    benchmark_path = (
        str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    )
    return {
        "schema": "glaciereq.make-it-heavy.semantic-support-benchmark-receipt.v2",
        "status": status,
        "benchmark_path": benchmark_path,
        "benchmark_sha256": sha256_text(raw_text),
        "source_repository": payload["source_repository"],
        "source_commit": payload["source_commit"],
        "case_count": case_count,
        "correct_count": correct,
        "exact_match_rate": exact_match_rate,
        "minimum_accuracy": minimum_accuracy,
        "cases": rows,
        "truth_boundary": payload["truth_boundary"],
    }


def failure_receipt(path: Path, error: Exception) -> Dict[str, object]:
    return {
        "schema": "glaciereq.make-it-heavy.semantic-support-benchmark-receipt.v2",
        "status": "FAIL",
        "benchmark_path": str(path),
        "error_type": type(error).__name__,
        "error": str(error),
        "case_count": 0,
        "correct_count": 0,
        "exact_match_rate": 0.0,
        "truth_boundary": (
            "Benchmark loading and scoring fail closed; malformed or missing evidence "
            "never counts as semantic-support success."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = args.benchmark.resolve()

    try:
        receipt = run_benchmark(path)
    except (BenchmarkValidationError, OSError, ValueError) as exc:
        receipt = failure_receipt(path, exc)

    text = json.dumps(receipt, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{text}\n", encoding="utf-8")
    print(text)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
