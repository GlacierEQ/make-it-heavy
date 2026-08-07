#!/usr/bin/env python3
"""Compare conservative V1 semantic support with the bounded Turn-6 V2 challenger."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Dict, List

from semantic_support import (
    SOURCE_ENTAILS_CLAIM,
    evaluate_source_span_support,
    sha256_text,
)
from semantic_support_v2 import evaluate_source_span_support_v2

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = ROOT / "benchmarks" / "turn6_semantic_recall.json"


def _evaluate(
    payload: Dict[str, object],
    evaluator: Callable,
) -> Dict[str, object]:
    spans = payload["source_spans"]
    rows: List[Dict[str, object]] = []
    by_split = defaultdict(lambda: Counter(total=0, correct=0, positives=0, positive_hits=0, false_entails=0))

    for case in payload["cases"]:
        pointer = case["pointer"]
        result = evaluator(case["claim"], spans[pointer], pointer)
        expected = case["expected"]
        actual = result.relation
        split = case["split"]
        passed = actual == expected
        bucket = by_split[split]
        bucket["total"] += 1
        bucket["correct"] += int(passed)
        if expected == SOURCE_ENTAILS_CLAIM:
            bucket["positives"] += 1
            bucket["positive_hits"] += int(actual == SOURCE_ENTAILS_CLAIM)
        elif actual == SOURCE_ENTAILS_CLAIM:
            bucket["false_entails"] += 1
        rows.append(
            {
                "id": case["id"],
                "split": split,
                "pointer": pointer,
                "expected": expected,
                "actual": actual,
                "pass": passed,
                "reason": result.reason,
                "token_coverage": result.token_coverage,
                "unsupported_numbers": list(result.unsupported_numbers),
                "unsupported_identifiers": list(result.unsupported_identifiers),
            }
        )

    summary = {}
    for split, counter in sorted(by_split.items()):
        positives = counter["positives"]
        summary[split] = {
            "total": counter["total"],
            "correct": counter["correct"],
            "accuracy": round(counter["correct"] / counter["total"], 4),
            "positive_recall": round(counter["positive_hits"] / positives, 4) if positives else None,
            "false_entails": counter["false_entails"],
        }

    return {
        "case_count": len(rows),
        "correct_count": sum(int(row["pass"]) for row in rows),
        "accuracy": round(sum(int(row["pass"]) for row in rows) / len(rows), 4),
        "splits": summary,
        "cases": rows,
    }


def run_benchmark(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    v1 = _evaluate(payload, evaluate_source_span_support)
    v2 = _evaluate(payload, evaluate_source_span_support_v2)
    contract = payload["promotion_contract"]

    tuning_recall = v2["splits"]["tuning"]["positive_recall"] or 0.0
    heldout_recall = v2["splits"]["held_out"]["positive_recall"] or 0.0
    negative_false_entails = v2["splits"]["negative_control"]["false_entails"]
    heldout_false_entails = v2["splits"]["held_out_negative"]["false_entails"]

    gates = {
        "tuning_recall": tuning_recall >= contract["minimum_positive_recall"],
        "heldout_positive_recall": heldout_recall >= contract["minimum_held_out_positive_recall"],
        "negative_precision": negative_false_entails <= contract["negative_false_entails_allowed"],
        "heldout_negative_precision": heldout_false_entails <= contract["held_out_false_entails_allowed"],
        "strictly_improves_total_accuracy": v2["accuracy"] > v1["accuracy"],
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    return {
        "schema": "glaciereq.make-it-heavy.turn6-semantic-recall-receipt.v1",
        "status": status,
        "benchmark_path": str(path.relative_to(ROOT)),
        "benchmark_sha256": sha256_text(path.read_text(encoding="utf-8")),
        "source_repository": payload["source_repository"],
        "source_commit": payload["source_commit"],
        "promotion_contract": contract,
        "gates": gates,
        "v1": v1,
        "v2": v2,
        "delta": {
            "accuracy": round(v2["accuracy"] - v1["accuracy"], 4),
            "tuning_positive_recall": round(
                (v2["splits"]["tuning"]["positive_recall"] or 0.0)
                - (v1["splits"]["tuning"]["positive_recall"] or 0.0),
                4,
            ),
            "heldout_positive_recall": round(
                (v2["splits"]["held_out"]["positive_recall"] or 0.0)
                - (v1["splits"]["held_out"]["positive_recall"] or 0.0),
                4,
            ),
        },
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
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
