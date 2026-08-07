import os
import tempfile
import unittest
from pathlib import Path

from health_memory import HealthAwareAdaptiveSwarmMemory
from innovation_health import (
    build_infrastructure_report,
    classify_shared_infrastructure_failure,
)
from innovation_loop import AdaptiveWorkerLoop


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"


class InnovationHealthTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.addCleanup(
            lambda: os.path.exists(self.db_path) and os.remove(self.db_path)
        )
        self.memory = HealthAwareAdaptiveSwarmMemory(self.db_path)
        self.loop = AdaptiveWorkerLoop(
            TEMPLATE_PATH,
            self.memory,
            min_workers=4,
            max_workers=8,
        )
        self.profiles = [
            {"role": template.role, "model": "shared-test-model"}
            for template in self.loop.templates
        ]

    def shared_failures(self):
        return [
            {
                "agent_id": index,
                "role": template.role,
                "model": "shared-test-model",
                "status": "error",
                "response": "Worker failed: OpenRouter returned HTTP 503: provider unavailable",
                "execution_time": 0.2 + index / 1000,
            }
            for index, template in enumerate(self.loop.templates)
        ]

    def test_shared_provider_failure_is_not_template_learning(self):
        results = self.shared_failures()
        incident = classify_shared_infrastructure_failure(results)
        self.assertIsNotNone(incident)
        self.assertFalse(incident["template_learning_eligible"])

        mission_id = self.memory.start_mission("provider outage")
        report = build_infrastructure_report(
            mission_id,
            "provider outage",
            results,
            self.loop,
            self.profiles,
            incident,
        )
        self.memory.persist_adaptive_turn(
            mission_id,
            report["scores"],
            report["adjustments"],
            report["current_worker_count"],
            report["next_worker_count"],
            report["topology_reason"],
            report,
        )

        self.assertEqual(report["health_class"], "INFRA_FAILURE")
        self.assertFalse(report["performance_valid"])
        self.assertTrue(
            all(
                item["action"] == "HOLD_TEMPLATE_INFRA"
                for item in report["adjustments"]
            )
        )
        self.assertEqual(self.memory.get_latest_template_adjustments(), {})
        self.assertEqual(
            self.memory.get_recent_worker_scores("source_mapper", limit=3), []
        )
        stats = self.memory.get_adaptive_stats()
        self.assertEqual(stats["total_worker_scores"], 8)
        self.assertEqual(stats["evaluated_worker_scores"], 0)
        self.assertEqual(stats["infrastructure_worker_scores"], 8)
        self.assertEqual(stats["avg_worker_quality"], 0.0)

    def test_mixed_turn_does_not_mask_worker_failure_as_infrastructure(self):
        results = self.shared_failures()
        results[0] = {
            "agent_id": 0,
            "role": self.loop.templates[0].role,
            "model": "shared-test-model",
            "status": "model_inference",
            "response": (
                "SOURCES\nSource: https://example.com\nHANDOFF\n"
                "Next verify the claim."
            ),
            "execution_time": 2.0,
        }
        self.assertIsNone(classify_shared_infrastructure_failure(results))

    def test_unrelated_worker_errors_do_not_trigger_shared_infra(self):
        results = self.shared_failures()
        for index, item in enumerate(results):
            item["response"] = f"Worker failed: role-specific parsing defect {index}"
            item["execution_time"] = 12.0 + index
        self.assertIsNone(classify_shared_infrastructure_failure(results))


if __name__ == "__main__":
    unittest.main()
