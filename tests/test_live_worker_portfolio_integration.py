import unittest
from pathlib import Path

from semantic_claim_innovation import ReceiptLineageSemanticClaimAdaptiveWorkerLoop


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "innovation_workers.yaml"
MANDATORY = ["source_mapper", "adversarial_breaker", "proof_engineer"]


class MemoryStub:
    def __init__(self, history):
        self.history = history

    def get_recent_worker_scores(self, role, limit=3):
        return list(self.history.get(role, ()))[:limit]


class LiveWorkerPortfolioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.scores = [
            {
                "role": "source_mapper",
                "quality_score": 80,
                "benefit_score": 0.65,
                "unique_contribution": 0.70,
            },
            {
                "role": "adversarial_breaker",
                "quality_score": 82,
                "benefit_score": 0.66,
                "unique_contribution": 0.70,
            },
            {
                "role": "proof_engineer",
                "quality_score": 83,
                "benefit_score": 0.67,
                "unique_contribution": 0.72,
            },
            {
                "role": "systems_architect",
                "quality_score": 94,
                "benefit_score": 0.88,
                "unique_contribution": 0.88,
            },
            {
                "role": "innovation_inventor",
                "quality_score": 79,
                "benefit_score": 0.60,
                "unique_contribution": 0.78,
            },
        ]

    def test_live_topology_uses_longitudinal_evidence_over_flashy_current_turn(self):
        history = {
            "systems_architect": [
                {
                    "quality_score": 30,
                    "benefit_score": 0.10,
                    "runtime_status": "model_inference",
                },
                {
                    "quality_score": 35,
                    "benefit_score": 0.12,
                    "runtime_status": "model_inference",
                },
            ],
            "innovation_inventor": [
                {
                    "quality_score": 91,
                    "benefit_score": 0.84,
                    "runtime_status": "model_inference",
                },
                {
                    "quality_score": 89,
                    "benefit_score": 0.81,
                    "runtime_status": "model_inference",
                },
            ],
        }
        loop = ReceiptLineageSemanticClaimAdaptiveWorkerLoop(
            TEMPLATE_PATH,
            MemoryStub(history),
            min_workers=4,
            max_workers=8,
        )

        selected = loop._next_roles(self.scores, 4)

        self.assertEqual(selected[:3], MANDATORY)
        self.assertEqual(selected[3], "innovation_inventor")
        telemetry = loop._last_worker_portfolio_selection
        self.assertEqual(telemetry["history_source"], "LONGITUDINAL_MEMORY")
        self.assertEqual(telemetry["selected_roles"], selected)
        self.assertGreater(
            telemetry["signals"]["innovation_inventor"]["portfolio_score"],
            telemetry["signals"]["systems_architect"]["portfolio_score"],
        )

    def test_no_memory_preserves_current_turn_fallback(self):
        loop = ReceiptLineageSemanticClaimAdaptiveWorkerLoop(
            TEMPLATE_PATH,
            None,
            min_workers=4,
            max_workers=8,
        )

        selected = loop._next_roles(self.scores, 4)

        self.assertEqual(selected[:3], MANDATORY)
        self.assertEqual(selected[3], "systems_architect")
        self.assertEqual(
            loop._last_worker_portfolio_selection["history_source"],
            "CURRENT_TURN_FALLBACK",
        )


if __name__ == "__main__":
    unittest.main()
