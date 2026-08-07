"""Regression tests for Turn-2 adaptive worker hardening."""

from pathlib import Path
import unittest

from adaptive_orchestrator import (
    bounded_provider_concurrency,
    effective_turn_timeout,
)
from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "innovation_workers.yaml"


class ClaimDisciplineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = ClaimAwareAdaptiveWorkerLoop(TEMPLATES)

    def test_classified_quantitative_claims_pass(self) -> None:
        response = """
OBSERVED[baseline-zero]: The recorded worker count is 8.
INFERENCE: The retained topology may indicate redundant coverage.
PROPOSED: Use a >90% threshold only as a hypothetical experiment value.
BLOCKED: Current employer adoption cannot be determined from the supplied packet.
"""
        gate = self.loop.evaluate_claim_discipline(response)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["unclassified_quantitative_count"], 0)
        self.assertEqual(gate["observed_source_count"], 1)

    def test_unsupported_metrics_fail_claim_gate(self) -> None:
        response = (
            "The candidate is verified at 82% confidence and will be production-ready "
            "in 2 weeks for more than 1000 users."
        )
        gate = self.loop.evaluate_claim_discipline(response)
        self.assertFalse(gate["pass"])
        self.assertGreater(gate["unclassified_quantitative_count"], 0)

    def test_claim_failure_caps_polished_structural_score(self) -> None:
        template = self.loop.template_for_role("source_mapper")
        assert template is not None
        response = """
SOURCES
SOURCE: https://example.com/control
SUPPORTED OBSERVATIONS
The system is verified at 95% confidence and will finish in 3 days.
CONTRADICTIONS OR GAPS
No gap is reported.
HANDOFF
Build the next proof artifact.
"""
        score = self.loop._score_one(
            template,
            {
                "agent_id": 0,
                "role": "source_mapper",
                "model": "test-model",
                "status": "model_inference",
                "response": response,
                "execution_time": 2.0,
            },
            novelty=1.0,
            peers=[],
        )
        self.assertFalse(score["claim_gate"]["pass"])
        self.assertLessEqual(score["quality_score"], 69.0)
        self.assertGreater(
            score["pre_claim_gate_quality_score"],
            score["quality_score"],
        )

    def test_task_includes_universal_claim_contract(self) -> None:
        tasks = self.loop.build_subtasks(
            "Inspect the proof slice.",
            [{"role": "source_mapper"}],
        )
        self.assertEqual(len(tasks), 1)
        self.assertIn("CLAIM DISCIPLINE — HARD GATE", tasks[0])
        self.assertIn("OBSERVED[source-id]", tasks[0])
        self.assertIn("PROPOSED", tasks[0])


class ProviderConcurrencyTests(unittest.TestCase):
    def test_provider_width_is_separate_from_logical_worker_count(self) -> None:
        self.assertEqual(bounded_provider_concurrency(7, 1), 1)
        self.assertEqual(bounded_provider_concurrency(7, 2), 2)
        self.assertEqual(bounded_provider_concurrency(7, 20), 7)

    def test_turn_timeout_scales_by_execution_waves(self) -> None:
        self.assertEqual(effective_turn_timeout(180, 7, 7), 180)
        self.assertEqual(effective_turn_timeout(180, 7, 2), 720)
        self.assertEqual(effective_turn_timeout(180, 7, 1), 1260)


if __name__ == "__main__":
    unittest.main()
