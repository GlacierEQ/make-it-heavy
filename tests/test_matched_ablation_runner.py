# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from external_experiment_lineage import ReceiptLineageClaimAwareAdaptiveWorkerLoop
from longitudinal_memory import LongitudinalAdaptiveSwarmMemory
from matched_ablation_runner import (
    MatchedAblationRunnerError,
    evaluate_system_outcome,
    execute_matched_worker_ablation,
)


class DeterministicExperimentOrchestrator:
    """Exercise the real persistence contract without provider/network dependence."""

    def __init__(self, db_path: str, roles: list[str]) -> None:
        self.memory = LongitudinalAdaptiveSwarmMemory(db_path)
        self.worker_profiles = [{"role": role} for role in roles]
        self.num_agents = len(roles)
        self.last_innovation_report: dict[str, Any] = {}
        self._current_mission_id = 0
        self._run_index = 0
        self.fail_on_run: int | None = None

    def orchestrate(self, user_input: str) -> str:
        context = ReceiptLineageClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
            user_input
        )
        if context is None:
            raise AssertionError("runner failed to provide experiment context")
        self._run_index += 1
        if self.fail_on_run == self._run_index:
            raise RuntimeError("injected provider failure")
        self._current_mission_id = self.memory.start_mission(user_input)
        roles = [str(profile["role"]) for profile in self.worker_profiles]
        quality = 92.0 if context["experiment_type"] == "BASELINE" else 68.0
        scores = [
            {
                "role": role,
                "template_id": f"template:{role}",
                "template_version": "v1",
                "quality_score": quality,
                "benefit_score": quality / 100.0,
                "unique_contribution": 0.8,
                "execution_time": 1.0 + index / 10.0,
                "runtime_status": "model_inference",
            }
            for index, role in enumerate(roles)
        ]
        report = {
            "scores": scores,
            "claim_gate_pass_rate": 1.0,
            "semantic_claim_gate_pass_rate": 1.0,
            "current_worker_count": len(roles),
            "next_worker_count": len(roles),
            "next_roles": roles,
            "topology_reason": "frozen test experiment",
        }
        self.memory.persist_longitudinal_turn(
            self._current_mission_id,
            context,
            scores,
            roles,
            report,
        )
        synthesis = f"observed run {self._run_index}: {'|'.join(roles)}"
        self.memory.complete_mission(
            self._current_mission_id,
            synthesis,
            status="completed",
        )
        self.last_innovation_report = report
        return synthesis


class MatchedAblationRunnerTests(unittest.TestCase):
    def test_system_outcome_rubric_is_bounded_and_deterministic(self) -> None:
        report = {
            "scores": [
                {"runtime_status": "model_inference", "quality_score": 80.0},
                {"runtime_status": "model_inference", "quality_score": 60.0},
            ],
            "claim_gate_pass_rate": 0.5,
            "semantic_claim_gate_pass_rate": None,
        }
        first = evaluate_system_outcome(report, "same synthesis")
        second = evaluate_system_outcome(report, "same synthesis")
        self.assertEqual(first, second)
        self.assertGreaterEqual(first.score, 0.0)
        self.assertLessEqual(first.score, 1.0)
        self.assertEqual(first.completion_rate, 1.0)
        self.assertEqual(first.average_quality, 0.7)
        self.assertEqual(first.semantic_claim_gate_pass_rate, 1.0)

    def test_executes_exact_pair_promotes_causal_value_and_restores_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            roles = ["source_mapper", "systems_architect", "proof_engineer"]
            orchestrator = DeterministicExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                roles,
            )
            receipt = execute_matched_worker_ablation(
                orchestrator,
                "Evaluate the same target architecture under a fixed evidence contract.",
                mission_family="job-restore-worker-science",
                comparison_key="candidate-A",
                remove_role="systems_architect",
            )

            self.assertEqual(
                receipt["status"],
                "MATCHED_ABLATION_EXECUTED_AND_RECORDED",
            )
            self.assertEqual(receipt["full"]["roles"], roles)
            self.assertEqual(
                receipt["ablated"]["roles"],
                ["source_mapper", "proof_engineer"],
            )
            self.assertEqual(receipt["removed_role"], "systems_architect")
            self.assertEqual(
                receipt["orchestrator_topology_restored"],
                {"roles": roles, "num_agents": 3},
            )
            self.assertEqual(
                [profile["role"] for profile in orchestrator.worker_profiles],
                roles,
            )
            self.assertEqual(orchestrator.num_agents, 3)
            self.assertGreater(
                receipt["causal_measurement"]["causal_measurement"][
                    "marginal_system_value"
                ],
                0.0,
            )

            parent_id = receipt["full"]["mission_id"]
            metrics = orchestrator.memory.get_longitudinal_metrics(parent_id)
            architect = next(
                row for row in metrics if row["agent_role"] == "systems_architect"
            )
            self.assertIsNotNone(architect["marginal_system_value"])
            self.assertIsNotNone(architect["outcome_leverage"])

    def test_restores_topology_when_ablated_execution_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            roles = ["source_mapper", "systems_architect", "proof_engineer"]
            orchestrator = DeterministicExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                roles,
            )
            orchestrator.fail_on_run = 2
            with self.assertRaisesRegex(RuntimeError, "injected provider failure"):
                execute_matched_worker_ablation(
                    orchestrator,
                    "mission",
                    mission_family="family",
                    comparison_key="key",
                    remove_role="systems_architect",
                )
            self.assertEqual(
                [profile["role"] for profile in orchestrator.worker_profiles],
                roles,
            )
            self.assertEqual(orchestrator.num_agents, 3)

    def test_rejects_unknown_removed_role_before_any_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = DeterministicExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                ["source_mapper", "proof_engineer"],
            )
            with self.assertRaisesRegex(
                MatchedAblationRunnerError,
                "remove_role is not active",
            ):
                execute_matched_worker_ablation(
                    orchestrator,
                    "mission",
                    mission_family="family",
                    comparison_key="key",
                    remove_role="systems_architect",
                )
            self.assertEqual(orchestrator._run_index, 0)

    def test_rejects_single_worker_topology_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = DeterministicExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                ["source_mapper"],
            )
            with self.assertRaisesRegex(
                MatchedAblationRunnerError,
                "at least two workers",
            ):
                execute_matched_worker_ablation(
                    orchestrator,
                    "mission",
                    mission_family="family",
                    comparison_key="key",
                    remove_role="source_mapper",
                )
            self.assertEqual(orchestrator._run_index, 0)


if __name__ == "__main__":
    unittest.main()
