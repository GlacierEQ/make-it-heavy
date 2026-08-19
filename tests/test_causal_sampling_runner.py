# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from causal_sampling_runner import (
    CausalSamplingError,
    execute_bounded_causal_turn,
    select_removal_role,
    should_sample,
)
from tests.test_matched_ablation_runner import DeterministicExperimentOrchestrator


class NormalCapableExperimentOrchestrator(DeterministicExperimentOrchestrator):
    """Support both ordinary production turns and experiment-tagged turns in tests."""

    def orchestrate(self, user_input: str) -> str:
        if "WORKER_EXPERIMENT_BEGIN" in user_input:
            return super().orchestrate(user_input)

        self._run_index += 1
        self._current_mission_id = self.memory.start_mission(user_input)
        roles = [str(profile["role"]) for profile in self.worker_profiles]
        synthesis = f"normal run {self._run_index}: {'|'.join(roles)}"
        self.memory.complete_mission(
            self._current_mission_id,
            synthesis,
            status="completed",
        )
        self.last_innovation_report = {
            "scores": [],
            "current_worker_count": len(roles),
            "next_worker_count": len(roles),
            "next_roles": roles,
            "topology_reason": "ordinary deterministic test turn",
        }
        return synthesis


class CausalSamplingRunnerTests(unittest.TestCase):
    def test_sampling_schedule_is_bounded_and_validated(self) -> None:
        self.assertFalse(should_sample(1, 3))
        self.assertFalse(should_sample(2, 3))
        self.assertTrue(should_sample(3, 3))
        self.assertTrue(should_sample(6, 3))
        with self.assertRaisesRegex(CausalSamplingError, "turn_index"):
            should_sample(0, 3)
        with self.assertRaisesRegex(CausalSamplingError, "sample_every"):
            should_sample(1, 0)

    def test_protected_roles_are_never_selected_and_optional_roles_rotate(self) -> None:
        profiles = [
            {"role": "source_mapper"},
            {"role": "systems_architect"},
            {"role": "innovation_inventor"},
            {"role": "adversarial_breaker"},
            {"role": "proof_engineer"},
        ]
        self.assertEqual(
            select_removal_role(
                profiles,
                turn_index=4,
                sample_every=4,
            ),
            "systems_architect",
        )
        self.assertEqual(
            select_removal_role(
                profiles,
                turn_index=8,
                sample_every=4,
            ),
            "innovation_inventor",
        )
        self.assertEqual(
            select_removal_role(
                profiles,
                turn_index=12,
                sample_every=4,
            ),
            "systems_architect",
        )

    def test_non_sample_turn_executes_exactly_one_normal_mission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = NormalCapableExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                ["source_mapper", "systems_architect", "proof_engineer"],
            )
            receipt = execute_bounded_causal_turn(
                orchestrator,
                "ordinary production mission",
                turn_index=1,
                sample_every=5,
                mission_family="job-restore",
                comparison_key="candidate-a",
            )
            self.assertEqual(receipt["status"], "NORMAL_TURN_EXECUTED")
            self.assertFalse(receipt["sampled"])
            self.assertEqual(receipt["reason"], "turn_not_due")
            self.assertEqual(orchestrator._run_index, 1)

    def test_sample_turn_executes_matched_pair_and_restores_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            roles = ["source_mapper", "systems_architect", "proof_engineer"]
            orchestrator = DeterministicExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                roles,
            )
            receipt = execute_bounded_causal_turn(
                orchestrator,
                "sampled production mission",
                turn_index=5,
                sample_every=5,
                mission_family="job-restore",
                comparison_key="candidate-a",
            )
            self.assertEqual(receipt["status"], "BOUNDED_CAUSAL_SAMPLE_EXECUTED")
            self.assertTrue(receipt["sampled"])
            self.assertEqual(receipt["selected_removal_role"], "systems_architect")
            self.assertEqual(orchestrator._run_index, 2)
            self.assertEqual(
                [profile["role"] for profile in orchestrator.worker_profiles],
                roles,
            )
            self.assertEqual(orchestrator.num_agents, 3)
            self.assertEqual(
                receipt["matched_ablation"]["status"],
                "MATCHED_ABLATION_EXECUTED_AND_RECORDED",
            )

    def test_due_turn_without_optional_role_degrades_to_one_normal_mission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = NormalCapableExperimentOrchestrator(
                str(Path(temp_dir) / "memory.db"),
                ["source_mapper", "proof_engineer"],
            )
            receipt = execute_bounded_causal_turn(
                orchestrator,
                "mission",
                turn_index=2,
                sample_every=2,
                mission_family="job-restore",
                comparison_key="candidate-a",
            )
            self.assertEqual(receipt["status"], "NORMAL_TURN_EXECUTED")
            self.assertEqual(receipt["reason"], "no_removable_optional_role")
            self.assertEqual(orchestrator._run_index, 1)

    def test_duplicate_topology_fails_before_execution(self) -> None:
        profiles = [{"role": "source_mapper"}, {"role": "source_mapper"}]
        with self.assertRaisesRegex(CausalSamplingError, "duplicate roles"):
            select_removal_role(profiles, turn_index=2, sample_every=2)


if __name__ == "__main__":
    unittest.main()
