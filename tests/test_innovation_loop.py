import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from innovation_loop import AdaptiveWorkerLoop
from innovation_memory import AdaptiveSwarmMemory


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"


def strong_response(role: str) -> str:
    return f"""
SOURCES
Source: https://example.com/{role}
Source: https://example.org/{role}
SUPPORTED OBSERVATIONS
Evidence supports a bounded observation with identifier `system/{role}` and 3 tests.
CONTRADICTIONS OR GAPS
The claim is uncertain and not proven without another receipt.
HANDOFF
Next, verify the implementation and measure the failure rate.
SYSTEM PATH
Input -> worker -> receipt -> decision.
CURRENT BOTTLENECK
The binding constraint is missing measured feedback.
BRICK WALL
The system cannot improve when worker contribution is invisible.
DISCONFIRMING TEST
Compare the adaptive topology against a fixed topology.
ARCHITECTURE
Use versioned templates, scorecards, memory, and a next-turn controller.
INTERFACES
WorkerResult, ScoreCard, Adjustment, TopologyDecision.
FAILURE DOMAINS
Bad evidence, redundant output, timeout, and scoring drift.
IMPLEMENTATION SLICE
Build the deterministic evaluator first.
ACCEPTANCE TEST
All workers receive a score and an adjustment.
ASSUMPTION TO BREAK
More workers do not automatically create more value.
INVENTION
Use marginal contribution to tune the topology.
WHY IT IS DIFFERENT
It changes prompts and worker count from measured performance.
FAST EXPERIMENT
Run two turns and compare quality and benefit.
KILL CRITERIA
Stop if both scores fall.
FAILURE ATTACKS
Workers may optimize for the grader.
FALSE-POSITIVE RISKS
Formatting can look complete while facts remain wrong.
SECURITY OR SAFETY RISKS
Do not let adaptation expand tool permissions.
MINIMUM HARDENING
Keep factual correctness outside the deterministic score.
STOP CONDITION
Rollback when quality and benefit both regress.
CLAIMS TO TEST
The loop records every worker and applies the next adjustment.
CURRENT EVIDENCE
The SQLite rows and JSON report provide receipts.
TEST HARNESS
Use unit tests with strong, weak, and timeout responses.
RECEIPTS
Persist scorecard and topology rows.
PASS FAIL CONTRACT
Pass only with zero worker omissions.
LEVERAGE MAP
One scorecard supports tuning, debugging, and presentation.
EXPECTED BENEFIT
Higher distinct contribution with lower redundancy.
COST AND DEPENDENCIES
SQLite and YAML only.
PRIORITY
Build now because the current runtime cannot learn.
NEXT BET
Add a human correctness score later.
PRIMARY AUDIENCE
The system operator.
ONE-SENTENCE THESIS
Every turn proves who helped and changes what happens next.
INFORMATION ORDER
Count, role, quality, benefit, adjustment.
PROOF TO SHOW
The worker report and persisted rows.
CONFUSION TO REMOVE
Quality score is not factual correctness.
"""


class AdaptiveWorkerLoopTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.addCleanup(
            lambda: os.path.exists(self.db_path) and os.remove(self.db_path)
        )
        self.memory = AdaptiveSwarmMemory(self.db_path)
        self.loop = AdaptiveWorkerLoop(
            TEMPLATE_PATH,
            self.memory,
            min_workers=4,
            max_workers=8,
        )

    def profiles(self):
        return [{"role": template.role} for template in self.loop.templates]

    def test_builds_eight_distinct_versioned_tasks(self):
        tasks = self.loop.build_subtasks("Improve the worker system", self.profiles())
        self.assertEqual(len(tasks), 8)
        self.assertEqual(len(set(tasks)), 8)
        self.assertIn("SOURCE MAPPER", tasks[0])
        self.assertIn("PRESENTATION STRATEGIST", tasks[-1])

    def test_scores_persists_and_adjusts_every_worker(self):
        mission_id = self.memory.start_mission("adaptive turn")
        results = [
            {
                "agent_id": index,
                "role": template.role,
                "model": "test-model",
                "status": "model_inference",
                "response": strong_response(template.role),
                "execution_time": 4.0 + index,
            }
            for index, template in enumerate(self.loop.templates)
        ]
        report = self.loop.evaluate_turn(
            mission_id,
            "adaptive turn",
            results,
            "bounded synthesis",
        )
        self.assertEqual(report["current_worker_count"], 8)
        self.assertEqual(len(report["scores"]), 8)
        self.assertEqual(len(report["adjustments"]), 8)
        self.assertEqual(report["silent_worker_omissions"], 0)
        self.assertIn("WORKER INNOVATION REPORT", report["markdown"])
        stats = self.memory.get_adaptive_stats()
        self.assertEqual(stats["total_worker_scores"], 8)
        self.assertEqual(stats["total_template_adjustments"], 8)
        self.assertIsNotNone(self.memory.get_last_topology_adjustment())

    def test_next_turn_includes_persisted_template_adjustment(self):
        mission_id = self.memory.start_mission("weak evidence")
        results = [
            {
                "agent_id": index,
                "role": template.role,
                "model": "test-model",
                "status": "model_inference",
                "response": "A short generic answer.",
                "execution_time": 10.0,
            }
            for index, template in enumerate(self.loop.templates)
        ]
        self.loop.evaluate_turn(
            mission_id,
            "weak evidence",
            results,
            "weak synthesis",
        )
        tasks = self.loop.build_subtasks("second turn", self.profiles())
        self.assertTrue(
            any("NEXT-TURN TEMPLATE ADJUSTMENT" in task for task in tasks)
        )
        self.assertTrue(
            any("Attach precise source pointers" in task for task in tasks)
        )

    def test_timeout_worker_is_not_scored_as_quality(self):
        mission_id = self.memory.start_mission("timeout")
        results = [
            {
                "agent_id": index,
                "role": template.role,
                "model": "test-model",
                "status": "timeout" if index == 0 else "model_inference",
                "response": (
                    "Worker exceeded timeout"
                    if index == 0
                    else strong_response(template.role)
                ),
                "execution_time": 180.0 if index == 0 else 5.0,
            }
            for index, template in enumerate(self.loop.templates)
        ]
        report = self.loop.evaluate_turn(
            mission_id,
            "timeout",
            results,
            "bounded synthesis",
        )
        first = report["scores"][0]
        first_adjustment = report["adjustments"][0]
        self.assertEqual(first["quality_score"], 0.0)
        self.assertEqual(first["benefit_score"], 0.0)
        self.assertEqual(first_adjustment["action"], "REPLACE_OR_NARROW")
        self.assertEqual(report["next_worker_count"], 8)

    def test_adaptive_orchestrator_appends_report_and_updates_topology(self):
        config = yaml.safe_load(
            (ROOT / "innovation_config.yaml").read_text(encoding="utf-8")
        )
        config["openrouter"]["api_key"] = "test-key"
        config["memory"]["db_path"] = self.db_path
        config["innovation"]["template_path"] = str(TEMPLATE_PATH)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            encoding="utf-8",
            delete=False,
        )
        yaml.safe_dump(config, handle, sort_keys=False)
        handle.close()
        self.addCleanup(
            lambda: os.path.exists(handle.name) and os.remove(handle.name)
        )

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                self.role = kwargs.get("role", "worker")

            def run(self, prompt):
                if self.role == "synthesis_reviewer":
                    return "Bounded synthesis preserving dissent."
                return strong_response(self.role)

        orchestrator = AdaptiveTaskOrchestrator(handle.name, silent=True)
        with patch("orchestrator.OpenRouterAgent", FakeAgent):
            result = orchestrator.orchestrate(
                "Improve the adaptive worker loop"
            )

        self.assertIn("WORKER INNOVATION REPORT", result)
        self.assertEqual(len(orchestrator.last_innovation_report["scores"]), 8)
        self.assertEqual(
            orchestrator.num_agents,
            orchestrator.last_innovation_report["next_worker_count"],
        )


if __name__ == "__main__":
    unittest.main()
