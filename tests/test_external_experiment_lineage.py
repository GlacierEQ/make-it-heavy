# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from external_experiment_lineage import (
    ReceiptLineageAdaptiveSwarmMemory,
    ReceiptLineageClaimAwareAdaptiveWorkerLoop,
)
from innovation_loop import InnovationConfigurationError
from longitudinal_innovation import WORKER_EXPERIMENT_BEGIN, WORKER_EXPERIMENT_END


def mission(payload: dict) -> str:
    return (
        f"{WORKER_EXPERIMENT_BEGIN}\n"
        f"{json.dumps(payload, sort_keys=True)}\n"
        f"{WORKER_EXPERIMENT_END}\n"
        "Matched external experiment."
    )


def score(role: str = "source_mapper") -> dict:
    return {
        "worker_id": 0,
        "role": role,
        "template_id": f"{role}.v1",
        "template_version": "v1",
        "model": "test-model",
        "runtime_status": "model_inference",
        "quality_score": 80.0,
        "benefit_score": 0.6,
        "unique_contribution": 0.5,
        "execution_time": 1.0,
    }


class ReceiptLineageParsingTests(unittest.TestCase):
    def test_template_delta_accepts_immutable_parent_receipt(self) -> None:
        ref = (
            "receipts/anthropic-worker-baseline-zero-2026-08-07.json@"
            "b94cfc04d6a73789e9564e2d5ee739c2f3115c70"
        )
        context = ReceiptLineageClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
            mission(
                {
                    "mission_family": "flagship_employer_bottleneck",
                    "comparison_key": "anthropic_agent_reliability_v1",
                    "experiment_type": "TEMPLATE_DELTA",
                    "parent_experiment_ref": ref,
                    "freeze_topology": True,
                    "template_changes": [
                        {
                            "role": "source_mapper",
                            "change_id": "source-nonclaim-preservation-v1",
                            "change_axis": "nonclaim_preservation",
                            "instruction": "Preserve NONCLAIM states.",
                            "hypothesis": "Evidence fidelity improves.",
                        }
                    ],
                }
            )
        )
        self.assertIsNotNone(context)
        assert context is not None
        self.assertIsNone(context["parent_mission_id"])
        self.assertEqual(context["parent_experiment_ref"], ref)
        self.assertEqual(context["schema"], "glaciereq.make-it-heavy.worker-experiment.v2")

    def test_rejects_ambiguous_dual_parent_lineage(self) -> None:
        with self.assertRaises(InnovationConfigurationError):
            ReceiptLineageClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
                mission(
                    {
                        "mission_family": "family",
                        "comparison_key": "key",
                        "experiment_type": "TEMPLATE_DELTA",
                        "parent_mission_id": 7,
                        "parent_experiment_ref": (
                            "receipts/control.json@"
                            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        ),
                        "template_changes": [
                            {
                                "role": "source_mapper",
                                "change_id": "c1",
                                "change_axis": "evidence",
                                "instruction": "Preserve state.",
                                "hypothesis": "Improve fidelity.",
                            }
                        ],
                    }
                )
            )

    def test_rejects_mutable_parent_ref(self) -> None:
        with self.assertRaises(InnovationConfigurationError):
            ReceiptLineageClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
                mission(
                    {
                        "mission_family": "family",
                        "comparison_key": "key",
                        "experiment_type": "ABLATION",
                        "parent_experiment_ref": "receipts/control.json@main",
                        "template_changes": [],
                    }
                )
            )

    def test_internal_parent_mission_remains_supported(self) -> None:
        context = ReceiptLineageClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
            mission(
                {
                    "mission_family": "family",
                    "comparison_key": "key",
                    "experiment_type": "TEMPLATE_DELTA",
                    "parent_mission_id": 3,
                    "template_changes": [
                        {
                            "role": "source_mapper",
                            "change_id": "c1",
                            "change_axis": "evidence",
                            "instruction": "Preserve state.",
                            "hypothesis": "Improve fidelity.",
                        }
                    ],
                }
            )
        )
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["parent_mission_id"], 3)
        self.assertIsNone(context["parent_experiment_ref"])


class ReceiptLineageMemoryTests(unittest.TestCase):
    def test_external_parent_ref_is_persisted_without_fake_mission_id(self) -> None:
        ref = (
            "receipts/anthropic-worker-baseline-zero-2026-08-07.json@"
            "b94cfc04d6a73789e9564e2d5ee739c2f3115c70"
        )
        with tempfile.TemporaryDirectory() as tmp:
            memory = ReceiptLineageAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            mission_id = memory.start_mission("matched external turn")
            context = {
                "mission_family": "flagship_employer_bottleneck",
                "comparison_key": "anthropic_agent_reliability_v1",
                "experiment_type": "TEMPLATE_DELTA",
                "parent_mission_id": None,
                "parent_experiment_ref": ref,
                "freeze_topology": True,
                "template_changes": [
                    {
                        "role": "source_mapper",
                        "change_id": "source-nonclaim-preservation-v1",
                        "change_axis": "nonclaim_preservation",
                        "instruction": "Preserve NONCLAIM states.",
                        "hypothesis": "Evidence fidelity improves.",
                    }
                ],
            }
            result = memory.persist_longitudinal_turn(
                mission_id,
                context,
                [score()],
                ["source_mapper"],
                {"mission_id": mission_id},
            )
            self.assertEqual(result["parent_experiment_ref"], ref)
            self.assertEqual(memory.get_external_parent_ref(mission_id), ref)
            metrics = memory.get_longitudinal_metrics(mission_id)
            self.assertEqual(len(metrics), 1)
            self.assertIsNone(metrics[0]["predecessor_mission_id"])


if __name__ == "__main__":
    unittest.main()
