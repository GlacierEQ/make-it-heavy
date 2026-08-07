"""Runtime compatibility tests for the V2 semantic batch adapter."""

import unittest

from semantic_support import SOURCE_ENTAILS_CLAIM, SOURCE_INSUFFICIENT
from semantic_support_v2_batch import evaluate_observed_claims_v2


COLLECTION_SPAN = (
    "collection_argv = pytest_collection_command(argv); "
    "collection_code, collection_output, collection_count = "
    "collect_pytest_count(argv, cwd, timeout, env); "
    "if collection_code != 0: return collection_code; "
    "if collection_count <= 0: return 3"
)
RECEIPT_SPAN = (
    'if receipt.get("observed_test_count") is None: raise SystemExit; '
    'if int(receipt.get("observed_test_count") or 0) <= 0: raise SystemExit'
)


class RuntimeSemanticV2Tests(unittest.TestCase):
    def test_v2_batch_recovers_reviewed_collection_paraphrase(self) -> None:
        response = (
            "OBSERVED[S1#E2]: Pytest collection must succeed and collect at least one "
            "item before verification continues."
        )
        receipt = evaluate_observed_claims_v2(response, {"S1#E2": COLLECTION_SPAN})

        self.assertTrue(receipt["semantic_gate_pass"])
        self.assertEqual(receipt["evaluator"], "semantic_support_v2")
        self.assertEqual(receipt["relation_counts"][SOURCE_ENTAILS_CLAIM], 1)

    def test_v2_batch_preserves_negative_outcome_precision(self) -> None:
        response = (
            "OBSERVED[S2#E2]: The receipt may report zero observed tests and still pass "
            "verification."
        )
        receipt = evaluate_observed_claims_v2(response, {"S2#E2": RECEIPT_SPAN})

        self.assertFalse(receipt["semantic_gate_pass"])
        self.assertEqual(receipt["relation_counts"][SOURCE_INSUFFICIENT], 1)

    def test_v2_batch_missing_span_fails_closed_with_existing_shape(self) -> None:
        response = "OBSERVED[S9#E9]: A precise claim without supplied span text."
        receipt = evaluate_observed_claims_v2(response, {})

        self.assertFalse(receipt["semantic_gate_pass"])
        self.assertEqual(receipt["observed_claim_count"], 1)
        self.assertEqual(receipt["missing_pointer_count"], 1)
        self.assertEqual(receipt["relation_counts"][SOURCE_INSUFFICIENT], 1)


if __name__ == "__main__":
    unittest.main()
