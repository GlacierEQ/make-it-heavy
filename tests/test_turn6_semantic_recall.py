import json
import unittest
from pathlib import Path

from scripts.run_turn6_semantic_recall import run_benchmark
from semantic_support import SOURCE_INSUFFICIENT
from semantic_support_v2 import (
    evaluate_source_span_support_v2,
    strip_citation_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "turn6_semantic_recall.json"


class Turn6SemanticRecallTests(unittest.TestCase):
    def test_citation_line_metadata_is_stripped_without_dropping_claim_text(self):
        value = strip_citation_metadata(
            "resolved commit SHA differs from expected (lines 41-46)"
        )
        self.assertEqual(value, "resolved commit SHA differs from expected")

    def test_new_numeric_precision_still_abstains(self):
        payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        span = payload["source_spans"]["S1#E2"]
        result = evaluate_source_span_support_v2(
            "The collection contains exactly 47 tests.",
            span,
            "S1#E2",
        )
        self.assertEqual(result.relation, SOURCE_INSUFFICIENT)

    def test_promotion_contract(self):
        receipt = run_benchmark(BENCHMARK)
        self.assertEqual(receipt["status"], "PASS", receipt)
        self.assertTrue(all(receipt["gates"].values()), receipt)
        self.assertGreater(receipt["delta"]["accuracy"], 0.0)
        self.assertGreaterEqual(
            receipt["v2"]["splits"]["tuning"]["positive_recall"], 0.75
        )
        self.assertGreaterEqual(
            receipt["v2"]["splits"]["held_out"]["positive_recall"], 0.60
        )
        self.assertEqual(
            receipt["v2"]["splits"]["negative_control"]["false_entails"], 0
        )
        self.assertEqual(
            receipt["v2"]["splits"]["held_out_negative"]["false_entails"], 0
        )


if __name__ == "__main__":
    unittest.main()
