# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from innovation_loop import InnovationConfigurationError
from longitudinal_innovation import (
    WORKER_EXPERIMENT_BEGIN,
    WORKER_EXPERIMENT_END,
    LongitudinalClaimAwareAdaptiveWorkerLoop,
)
from longitudinal_memory import LongitudinalAdaptiveSwarmMemory


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"


def experiment_block(payload: dict) -> str:
    return (
        f"{WORKER_EXPERIMENT_BEGIN}\n"
        f"{json.dumps(payload, sort_keys=True)}\n"
        f"{WORKER_EXPERIMENT_END}\n"
        "Investigate the supplied system without changing the experiment controls."
    )


def score(role: str, quality: float, benefit: float, unique: float = 0.5) -> dict:
    return {
        "worker_id": 0,
        "role": role,
        "template_id": f"worker.{role}.1",
        "template_version": "1",
        "model": "test-model",
        "runtime_status": "model_inference",
        "quality_score": quality,
        "benefit_score": benefit,
        "unique_contribution": unique,
        "execution_time": 2.5,
    }


class LongitudinalExperimentParsingTests(unittest.TestCase):
    def test_baseline_rejects_template_changes(self) -> None:
        mission = experiment_block(
            {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "frontier_lab_v1",
                "experiment_type": "BASELINE",
                "template_changes": [
                    {
                        "role": "source_mapper",
                        "change_id": "c1",
                        "change_axis": "evidence_density",
                        "instruction": "Use two source classes.",
                        "hypothesis": "Evidence density rises.",
                    }
                ],
            }
        )
        with self.assertRaises(InnovationConfigurationError):
            LongitudinalClaimAwareAdaptiveWorkerLoop.parse_experiment_context(mission)

    def test_template_delta_enforces_one_change_per_worker(self) -> None:
        mission = experiment_block(
            {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "frontier_lab_v1",
                "experiment_type": "TEMPLATE_DELTA",
                "parent_mission_id": 1,
                "template_changes": [
                    {
                        "role": "source_mapper",
                        "change_id": "c1",
                        "change_axis": "evidence_density",
                        "instruction": "Use two source classes.",
                        "hypothesis": "Evidence density rises.",
                    },
                    {
                        "role": "source_mapper",
                        "change_id": "c2",
                        "change_axis": "scope",
                        "instruction": "Narrow the source surface.",
                        "hypothesis": "Precision rises.",
                    },
                ],
            }
        )
        with self.assertRaises(InnovationConfigurationError):
            LongitudinalClaimAwareAdaptiveWorkerLoop.parse_experiment_context(mission)

    def test_experiment_metadata_is_removed_from_worker_mission(self) -> None:
        mission = experiment_block(
            {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "frontier_lab_v1",
                "experiment_type": "BASELINE",
                "freeze_topology": True,
                "template_changes": [],
            }
        )
        stripped = LongitudinalClaimAwareAdaptiveWorkerLoop.mission_without_experiment_block(
            mission
        )
        self.assertNotIn(WORKER_EXPERIMENT_BEGIN, stripped)
        self.assertNotIn("mission_family", stripped)
        self.assertIn("Investigate the supplied system", stripped)


class LongitudinalPromptIsolationTests(unittest.TestCase):
    def test_experiment_does_not_inherit_legacy_latest_adjustment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            legacy_mission = memory.start_mission("legacy adjustment seed")
            memory.log_template_adjustment(
                legacy_mission,
                {
                    "role": "source_mapper",
                    "template_id": "source_mapper.v1",
                    "action": "TIGHTEN_EVIDENCE",
                    "instruction": "THIS MUST NOT LEAK INTO THE BASELINE",
                    "quality_before": 70.0,
                    "quality_after": 71.0,
                    "benefit_before": 0.5,
                    "benefit_after": 0.51,
                },
            )
            loop = LongitudinalClaimAwareAdaptiveWorkerLoop(
                TEMPLATE_PATH,
                memory,
                min_workers=4,
                max_workers=8,
            )
            mission = experiment_block(
                {
                    "mission_family": "flagship_employer_bottleneck",
                    "comparison_key": "frontier_lab_v1",
                    "experiment_type": "BASELINE",
                    "freeze_topology": True,
                    "template_changes": [],
                }
            )
            task = loop.build_subtasks(
                mission,
                [{"role": "source_mapper", "model": "test-model"}],
            )[0]
            self.assertNotIn("THIS MUST NOT LEAK", task)
            self.assertIn("Preserve this worker's baseline contract", task)
            self.assertIn("LONGITUDINAL EXPERIMENT CONTRACT", task)


class LongitudinalMemoryTests(unittest.TestCase):
    def test_same_family_predecessor_and_quality_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            first = memory.start_mission("baseline mission")
            base_context = {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "frontier_lab_v1",
                "experiment_type": "BASELINE",
                "parent_mission_id": None,
                "freeze_topology": True,
                "template_changes": [],
            }
            memory.persist_longitudinal_turn(
                first,
                base_context,
                [score("source_mapper", 80.0, 0.61)],
                ["source_mapper"],
                {"mission_id": first},
            )

            second = memory.start_mission("matched mission turn two")
            delta_context = {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "frontier_lab_v1",
                "experiment_type": "TEMPLATE_DELTA",
                "parent_mission_id": first,
                "freeze_topology": True,
                "template_changes": [
                    {
                        "role": "source_mapper",
                        "change_id": "source-density-v2",
                        "change_axis": "evidence_density",
                        "instruction": "Require a second independent source class.",
                        "hypothesis": "Source quality rises without scope expansion.",
                    }
                ],
            }
            result = memory.persist_longitudinal_turn(
                second,
                delta_context,
                [score("source_mapper", 86.5, 0.65)],
                ["source_mapper"],
                {"mission_id": second},
            )
            metric = result["metrics"][0]
            self.assertEqual(metric["predecessor_mission_id"], first)
            self.assertEqual(metric["quality_delta"], 6.5)
            self.assertIsNone(metric["marginal_system_value"])
            self.assertIsNone(metric["outcome_leverage"])

    def test_different_comparison_key_is_not_treated_as_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            first = memory.start_mission("family a")
            memory.persist_longitudinal_turn(
                first,
                {
                    "mission_family": "employer_bottleneck",
                    "comparison_key": "company_class_a",
                    "experiment_type": "BASELINE",
                    "parent_mission_id": None,
                    "freeze_topology": True,
                    "template_changes": [],
                },
                [score("proof_engineer", 84.0, 0.7)],
                ["proof_engineer"],
                {"mission_id": first},
            )
            second = memory.start_mission("family b")
            result = memory.persist_longitudinal_turn(
                second,
                {
                    "mission_family": "employer_bottleneck",
                    "comparison_key": "company_class_b",
                    "experiment_type": "BASELINE",
                    "parent_mission_id": None,
                    "freeze_topology": True,
                    "template_changes": [],
                },
                [score("proof_engineer", 90.0, 0.8)],
                ["proof_engineer"],
                {"mission_id": second},
            )
            self.assertIsNone(result["metrics"][0]["predecessor_mission_id"])
            self.assertIsNone(result["metrics"][0]["quality_delta"])

    def test_ablation_populates_causal_metrics_without_relabeling_heuristic_benefit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            mission_id = memory.start_mission("ablation-ready baseline")
            memory.persist_longitudinal_turn(
                mission_id,
                {
                    "mission_family": "flagship_employer_bottleneck",
                    "comparison_key": "frontier_lab_v1",
                    "experiment_type": "BASELINE",
                    "parent_mission_id": None,
                    "freeze_topology": True,
                    "template_changes": [],
                },
                [score("proof_engineer", 92.0, 0.88, unique=0.7)],
                ["proof_engineer"],
                {"mission_id": mission_id},
            )
            ablation = memory.record_worker_ablation(
                mission_id,
                "proof_engineer",
                full_outcome_score=0.91,
                ablated_outcome_score=0.69,
                outcome_leverage=0.82,
                decision_changed=True,
                details={"unsupported_claims_delta": 4},
            )
            self.assertEqual(ablation["marginal_system_value"], 0.22)
            metrics = memory.get_longitudinal_metrics(mission_id)
            self.assertEqual(metrics[0]["heuristic_benefit_score"], 0.88)
            self.assertEqual(metrics[0]["marginal_system_value"], 0.22)
            self.assertEqual(metrics[0]["outcome_leverage"], 0.82)


if __name__ == "__main__":
    unittest.main()
