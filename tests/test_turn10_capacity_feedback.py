"""Turn-10 adaptive provider-capacity feedback tests."""

from pathlib import Path
import unittest

from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop
from innovation_health import (
    classify_provider_capacity_contention,
    mark_capacity_failures,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "innovation_workers.yaml"


class CapacityClassificationTests(unittest.TestCase):
    @staticmethod
    def _results():
        return [
            {
                "agent_id": 0,
                "role": "source_mapper",
                "model": "qwen3:0.6b",
                "status": "model_inference",
                "response": "OBSERVED[S1]: bounded evidence.",
                "execution_time": 50.0,
            },
            {
                "agent_id": 1,
                "role": "bottleneck_cartographer",
                "model": "qwen3:0.6b",
                "status": "error",
                "response": "Worker failed: request timed out after 120s",
                "execution_time": 368.0,
            },
        ]

    def test_local_partial_timeout_is_capacity_contention(self) -> None:
        incident = classify_provider_capacity_contention(
            self._results(),
            base_url="http://127.0.0.1:11434/v1",
            current_provider_width=8,
        )
        self.assertIsNotNone(incident)
        assert incident is not None
        self.assertEqual(incident["failed_worker_ids"], [1])
        self.assertEqual(incident["recommended_provider_concurrency_width"], 4)

        marked = mark_capacity_failures(self._results(), incident)
        self.assertEqual(marked[0]["status"], "model_inference")
        self.assertEqual(marked[1]["status"], "capacity_failure")
        self.assertFalse(marked[1]["template_learning_eligible"])

    def test_hosted_partial_timeout_is_not_assumed_capacity(self) -> None:
        incident = classify_provider_capacity_contention(
            self._results(),
            base_url="https://api.openai.com/v1",
            current_provider_width=8,
        )
        self.assertIsNone(incident)


class CapacityLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = ClaimAwareAdaptiveWorkerLoop(TEMPLATES, min_workers=4, max_workers=8)

    def _capacity_score(self):
        return {
            "role": "bottleneck_cartographer",
            "template_id": "bottleneck_cartographer.v1",
            "runtime_status": "capacity_failure",
            "quality_score": 0.0,
            "benefit_score": 0.0,
            "dimensions": {
                "completion": 0.0,
                "evidence": 0.0,
                "specificity": 0.0,
                "novelty": 0.0,
                "actionability": 0.0,
                "truth": 0.0,
                "efficiency": 0.0,
            },
        }

    def test_capacity_failure_does_not_rewrite_template(self) -> None:
        adjustment = self.loop._adjustment(self._capacity_score())
        self.assertEqual(adjustment["action"], "HOLD_TEMPLATE_CAPACITY")
        self.assertIn("Preserve this template unchanged", adjustment["instruction"])

    def test_capacity_failure_halves_provider_width(self) -> None:
        width, reason = self.loop._next_provider_width(
            [self._capacity_score()],
            current_width=8,
            logical_worker_count=8,
        )
        self.assertEqual(width, 4)
        self.assertIn("measured capacity contention", reason)

    def test_clean_reduced_width_holds(self) -> None:
        score = dict(self._capacity_score())
        score["runtime_status"] = "model_inference"
        width, reason = self.loop._next_provider_width(
            [score],
            current_width=4,
            logical_worker_count=8,
        )
        self.assertEqual(width, 4)
        self.assertIn("matched clean turn", reason)


if __name__ == "__main__":
    unittest.main()
