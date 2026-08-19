# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from longitudinal_memory import LongitudinalAdaptiveSwarmMemory
from matched_ablation import MatchedAblationError, record_matched_worker_ablation


def score(role: str, quality: float = 88.0, benefit: float = 0.72) -> dict:
    return {
        "worker_id": 0,
        "role": role,
        "template_id": f"worker.{role}.1",
        "template_version": "1",
        "model": "test-model",
        "runtime_status": "model_inference",
        "quality_score": quality,
        "benefit_score": benefit,
        "unique_contribution": 0.6,
        "execution_time": 1.2,
    }


def context(kind: str, parent: int | None = None) -> dict:
    return {
        "mission_family": "job-ecosystem-worker-science",
        "comparison_key": "portfolio-v1",
        "experiment_type": kind,
        "parent_mission_id": parent,
        "freeze_topology": True,
        "template_changes": [],
    }


class MatchedAblationTests(unittest.TestCase):
    def _memory(self, tmp: str) -> LongitudinalAdaptiveSwarmMemory:
        return LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))

    def _baseline(self, memory: LongitudinalAdaptiveSwarmMemory) -> int:
        mission_id = memory.start_mission("full topology")
        memory.persist_longitudinal_turn(
            mission_id,
            context("BASELINE"),
            [score("source_mapper"), score("proof_engineer", 94.0, 0.86)],
            ["source_mapper", "proof_engineer"],
            {"mission_id": mission_id},
        )
        return mission_id

    def test_matched_execution_promotes_causal_value_into_live_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            parent = self._baseline(memory)
            ablated = memory.start_mission("proof engineer removed")
            memory.persist_longitudinal_turn(
                ablated,
                context("ABLATION", parent),
                [score("source_mapper", 81.0, 0.61)],
                ["source_mapper"],
                {"mission_id": ablated},
            )

            receipt = record_matched_worker_ablation(
                memory,
                ablated,
                full_outcome_score=0.93,
                ablated_outcome_score=0.66,
                outcome_leverage=0.88,
                decision_changed=True,
                details={"rubric": "application-quality-v1"},
            )

            self.assertEqual(receipt["status"], "CAUSAL_MEASUREMENT_RECORDED")
            self.assertEqual(receipt["removed_role"], "proof_engineer")
            self.assertEqual(
                receipt["causal_measurement"]["marginal_system_value"], 0.27
            )
            history = memory.get_recent_worker_portfolio_history("proof_engineer")
            self.assertEqual(history[0]["marginal_system_value"], 0.27)
            self.assertEqual(history[0]["outcome_leverage"], 0.88)

    def test_same_topology_is_rejected_as_non_counterfactual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            parent = self._baseline(memory)
            ablated = memory.start_mission("invalid no-op ablation")
            memory.persist_longitudinal_turn(
                ablated,
                context("ABLATION", parent),
                [score("source_mapper"), score("proof_engineer")],
                ["source_mapper", "proof_engineer"],
                {"mission_id": ablated},
            )
            with self.assertRaisesRegex(MatchedAblationError, "remove exactly one"):
                record_matched_worker_ablation(
                    memory,
                    ablated,
                    full_outcome_score=0.9,
                    ablated_outcome_score=0.8,
                    outcome_leverage=0.4,
                    decision_changed=False,
                )

    def test_observational_child_cannot_be_promoted_to_causal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._memory(tmp)
            parent = self._baseline(memory)
            child = memory.start_mission("observation with one role")
            memory.persist_longitudinal_turn(
                child,
                context("OBSERVATION", parent),
                [score("source_mapper")],
                ["source_mapper"],
                {"mission_id": child},
            )
            with self.assertRaisesRegex(MatchedAblationError, "must be an ABLATION"):
                record_matched_worker_ablation(
                    memory,
                    child,
                    full_outcome_score=0.9,
                    ablated_outcome_score=0.7,
                    outcome_leverage=0.6,
                    decision_changed=True,
                )


if __name__ == "__main__":
    unittest.main()
