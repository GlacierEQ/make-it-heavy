"""Hardening regressions for the adaptive worker runtime."""

import tempfile
import unittest

import yaml
from pathlib import Path

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from innovation_loop import AdaptiveWorkerLoop, InnovationConfigurationError, MANDATORY_ROLES
from innovation_memory import AdaptiveSwarmMemory

ROOT = Path(__file__).resolve().parents[1]


class AdaptiveHardeningTests(unittest.TestCase):
    def test_empty_results_fail_explicitly(self):
        memory = AdaptiveSwarmMemory(":memory:")
        loop = AdaptiveWorkerLoop(ROOT / "templates/innovation_workers.yaml", memory)
        with self.assertRaisesRegex(InnovationConfigurationError, "at least one"):
            loop.evaluate_turn(1, "mission", [], "")

    def test_max_workers_clamps_to_template_count(self):
        loop = AdaptiveWorkerLoop(
            ROOT / "templates/innovation_workers.yaml",
            max_workers=16,
        )
        self.assertEqual(loop.max_workers, len(loop.templates))

    def test_mandatory_roles_are_restored(self):
        loop = AdaptiveWorkerLoop(ROOT / "templates/innovation_workers.yaml")
        scores = [
            {
                "role": "systems_architect",
                "quality_score": 90.0,
                "benefit_score": 0.9,
                "runtime_status": "model_inference",
            }
        ]
        roles = loop._next_roles(scores, 4)
        for role in MANDATORY_ROLES:
            self.assertIn(role, roles)

    def test_atomic_turn_rejects_unknown_mission(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = AdaptiveSwarmMemory(str(Path(directory) / "memory.db"))
            with self.assertRaisesRegex(ValueError, "unknown mission_id"):
                memory.persist_adaptive_turn(999, [], [], 0, 0, "none", {})
            stats = memory.get_adaptive_stats()
            self.assertEqual(stats["total_worker_scores"], 0)
            self.assertEqual(stats["total_template_adjustments"], 0)
            self.assertEqual(stats["total_topology_adjustments"], 0)

    def test_persisted_topology_restores_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = yaml.safe_load((ROOT / "innovation_config.yaml").read_text())
            config["openrouter"]["api_key"] = "test"
            config["memory"]["db_path"] = str(Path(directory) / "memory.db")
            config['innovation']['template_path'] = str(ROOT / 'templates/innovation_workers.yaml')
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            # Constructor validation is covered without making network calls.
            first = AdaptiveTaskOrchestrator(str(config_path), silent=True)
            mission_id = first.memory.start_mission("persist topology")
            report = {"next_roles": list(MANDATORY_ROLES) + ["systems_architect"]}
            first.memory.log_topology_adjustment(
                mission_id, 8, 4, "test", report
            )
            second = AdaptiveTaskOrchestrator(str(config_path), silent=True)
            self.assertEqual(second.num_agents, 4)
            self.assertEqual(
                [profile["role"] for profile in second.worker_profiles],
                report["next_roles"],
            )


if __name__ == "__main__":
    unittest.main()
