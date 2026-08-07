"""Regression tests for the durable Turn-3 investigator receipt."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "receipts" / "worker-turn-03-2026-08-07.json"
SUMMARY = ROOT / "artifacts" / "worker-turn-03" / "summary.md"


class Turn3ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_turn3_execution_identity_is_complete(self) -> None:
        receipt = self.receipt
        self.assertEqual(receipt["schema"], "glaciereq.make-it-heavy.worker-turn-receipt.v3")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["turn_number"], 3)
        self.assertEqual(receipt["provider_count"], 1)
        self.assertEqual(receipt["logical_worker_count"], 7)
        self.assertEqual(receipt["provider_concurrency_width"], 1)
        self.assertEqual(receipt["valid_worker_receipts"], 7)
        self.assertEqual(receipt["silent_worker_omissions"], 0)
        self.assertEqual(receipt["capability_count"], 19)
        self.assertEqual(receipt["same_turn_tuning_events"], 3)
        self.assertEqual(receipt["closed_tuning_events"], 3)
        self.assertEqual(
            receipt["result_sha256"],
            "37587e6ba3d59e0511e2c78041506c42c75eeac41ca30f75eb8a5307ff53acab",
        )

    def test_all_seven_lanes_are_unique_and_content_addressed(self) -> None:
        lanes = self.receipt["lanes"]
        roles = [lane["role"] for lane in lanes]
        self.assertEqual(len(lanes), 7)
        self.assertEqual(len(set(roles)), 7)
        self.assertEqual(sum(lane["attempt_count"] for lane in lanes), 19)
        for lane in lanes:
            digest = lane["response_sha256"]
            self.assertEqual(len(digest), 64)
            self.assertTrue(all(char in "0123456789abcdef" for char in digest))
            self.assertEqual(lane["attempt_count"], len(lane["capability_ids"]))

    def test_semantic_quarantine_prevents_worker_consensus_from_becoming_truth(self) -> None:
        receipt = self.receipt
        self.assertEqual(
            receipt["promotion_status"],
            "ACTIONABLE_WITH_SEMANTIC_QUARANTINE",
        )
        self.assertEqual(
            set(receipt["semantic_quarantine"]),
            {lane["role"] for lane in receipt["lanes"]},
        )
        self.assertGreaterEqual(len(receipt["accepted_findings"]), 5)
        self.assertIn("does not promote quarantined worker prose", receipt["truth_boundary"])

    def test_fresh_head_lineage_and_expected_head_promotion_are_preserved(self) -> None:
        execution = self.receipt["downstream_execution"]
        self.assertEqual(
            execution["baseline_repair"]["canonical_commit"],
            "4008d20be09401330059d07df0f90f6e9505fe21",
        )
        self.assertEqual(
            execution["stale_proof_branch"]["disposition"],
            "CLOSED_UNMERGED_SUPERSEDED",
        )
        proof = execution["fresh_proof_synthesis"]
        self.assertEqual(proof["pull_request"], 45)
        self.assertEqual(
            proof["verified_head"],
            "5f922b53cba13ff7a7db401df0ecc02a6c1957bb",
        )
        self.assertEqual(
            proof["canonical_commit"],
            "b613a70766586511199266d63499bd31d2808b97",
        )
        self.assertEqual(proof["promotion"], "SQUASH_MERGED_WITH_EXPECTED_HEAD_GUARD")

    def test_all_required_helix_gates_passed(self) -> None:
        gates = self.receipt["verification"]["gates"]
        self.assertEqual(
            set(gates),
            {
                "CI",
                "Application Registry Validation",
                "Portfolio Root Truth",
                "Proof Identity Self Verification",
                "Proof-weighted portfolio audit",
            },
        )
        self.assertTrue(all(value == "PASS" for value in gates.values()))

    def test_independent_readback_keeps_identity_separate_from_workload_result(self) -> None:
        readback = self.receipt["verification"]["independent_artifact_readback"]
        self.assertEqual(readback["receipt_ref"], "main")
        self.assertEqual(readback["identity_status"], "RESOLVED")
        self.assertEqual(
            readback["resolved_commit_sha"],
            "ba24e028c7ce50e407b50019768be1dd8780b0b9",
        )
        self.assertEqual(readback["workload_status"], "FAILED")

    def test_summary_exists_and_points_back_to_durable_receipt(self) -> None:
        text = SUMMARY.read_text(encoding="utf-8")
        self.assertIn("worker-turn-03-2026-08-07.json", text)
        self.assertIn("semantic entailment", text)
        self.assertIn("b613a70766586511199266d63499bd31d2808b97", text)


if __name__ == "__main__":
    unittest.main()
