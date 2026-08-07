#!/usr/bin/env python3
"""Run the bounded Turn-5 source-span semantic support benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from semantic_support import evaluate_source_span_support, sha256_text

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = ROOT / "benchmarks" / "turn5_semantic_support.json"


def run_benchmark(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    spans = payload["source_spans"]
    rows: List[Dict[str, object]] = []
    correct = 0

    for case in payload["cases"]:
        pointer = case["pointer"]
        span_text = spans[pointer]
        result = evaluate_source_span_support(
            case["claim"],
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
                "origin": case["origin"],
            }
        )

    case_count = len(rows)
    return {
        "schema": "glaciereq.make-it-heavy.semantic-support-benchmark-receipt.v1",
        "status": "PASS" if correct == case_count else "FAIL",
        "benchmark_path": str(path.relative_to(ROOT)),
        "benchmark_sha256": sha256_text(path.read_text(encoding="utf-8")),
        "source_repository": payload["source_repository"],
        "source_commit": payload["source_commit"],
        "case_count": case_count,
        "correct_count": correct,
        "exact_match_rate": round(correct / case_count, 4) if case_count else 0.0,
        "cases": rows,
        "truth_boundary": payload["truth_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipt = run_benchmark(args.benchmark.resolve())
    text = json.dumps(receipt, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{text}\n", encoding="utf-8")
    print(text)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
