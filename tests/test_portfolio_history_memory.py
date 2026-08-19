# SPDX-License-Identifier: Proprietary
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from health_memory import HealthAwareAdaptiveSwarmMemory
from longitudinal_memory import LongitudinalAdaptiveSwarmMemory
from semantic_claim_innovation import ReceiptLineageSemanticClaimAdaptiveWorkerLoop


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"
MANDATORY = ["source_mapper", "adversarial_breaker", "proof_engineer"]


def score(
    role: str,
    *,
    runtime_status: str = "model_inference",
    quality: float = 80.0,
    benefit: float = 0.70,
    unique: float = 0.60,
) -> dict:
    return {
        "worker_id": 1,
        "role": role,
        "template_id": f"worker.{role}.1",
        "template_version": "1",
        "model": "test-model",
        "runtime_status": runtime_status,
        "quality_score": quality,
        "benefit_score": benefit,
        "unique_contribution": unique,
        "execution_time": 1.5,
    }


class PortfolioHistoryMemoryTests(unittest.TestCase):
    def test_role_failure_is_visible_but_shared_infrastructure_is_not_penalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = HealthAwareAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            mission_id = memory.start_mission("portfolio reliability evidence")
            memory.log_worker_score(
                mission_id,
                score("systems_architect", quality=91.0, benefit=0.88, unique=0.82),
            )
            memory.log_worker_score(
                mission_id,
                score(
                    "systems_architect",
                    runtime_status="error",
                    quality=0.0,
                    benefit=0.0,
                    unique=0.0,
                ),
            )
            memory.log_worker_score(
                mission_id,
                score(
                    "systems_architect",
                    runtime_status="infra_failure",
                    quality=0.0,
                    benefit=0.0,
                    unique=0.0,
                ),
            )

            history = memory.get_recent_worker_portfolio_history(
                "systems_architect",
                limit=8,
            )

            self.assertEqual(
                [row["runtime_status"] for row in history],
                ["error", "model_inference"],
            )
            self.assertFalse(history[0]["performance_valid"])
            self.assertTrue(history[1]["performance_valid"])
            self.assertEqual(history[1]["unique_contribution"], 0.82)
            self.assertEqual(
                len(memory.get_recent_worker_scores("systems_architect", limit=8)),
                1,
            )

    def test_explicit_ablation_metrics_reach_portfolio_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = LongitudinalAdaptiveSwarmMemory(str(Path(tmp) / "memory.db"))
            mission_id = memory.start_mission("causal portfolio evidence")
            worker = score(
                "innovation_inventor",
                quality=90.0,
                benefit=0.84,
                unique=0.75,
            )
            memory.log_worker_score(mission_id, worker)
            memory.persist_longitudinal_turn(
                mission_id,
                {
                    "mission_family": "job_ecosystem_restoration",
                    "comparison_key": "portfolio-causal-v1",
                    "experiment_type": "BASELINE",
                    "parent_mission_id": None,
                    "freeze_topology": True,
                    "template_changes": [],
                },
                [worker],
                ["innovation_inventor"],
                {"mission_id": mission_id},
            )
            memory.record_worker_ablation(
                mission_id,
                "innovation_inventor",
                full_outcome_score=0.91,
                ablated_outcome_score=0.66,
                outcome_leverage=0.80,
                decision_changed=True,
                details={"proof": "counterfactual worker removal"},
            )

            history = memory.get_recent_worker_portfolio_history(
                "innovation_inventor",
                limit=8,
            )

            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["heuristic_benefit_score"], 0.84)
            self.assertEqual(history[0]["unique_contribution_score"], 0.75)
            self.assertEqual(history[0]["marginal_system_value"], 0.25)
            self.assertEqual(history[0]["outcome_leverage"], 0.80)
            self.assertTrue(history[0]["performance_valid"])

    def test_live_selector_prefers_richer_portfolio_history_contract(self) -> None:
        class DualMemory:
            def get_recent_worker_portfolio_history(self, role, limit=8):
                if role == "innovation_inventor":
                    return [
                        {
                            "quality_score": 92,
                            "benefit_score": 0.86,
                            "unique_contribution_score": 0.82,
                            "runtime_status": "model_inference",
                            "performance_valid": True,
                            "marginal_system_value": 0.35,
                            "outcome_leverage": 0.90,
                        }
                    ][:limit]
                if role == "systems_architect":
                    return [
                        {
                            "quality_score": 95,
                            "benefit_score": 0.90,
                            "runtime_status": "error",
                            "performance_valid": False,
                        },
                        {
                            "quality_score": 40,
                            "benefit_score": 0.20,
                            "runtime_status": "model_inference",
                            "performance_valid": True,
                        },
                    ][:limit]
                return []

            def get_recent_worker_scores(self, role, limit=3):
                # Deliberately favors systems_architect. The live loop must not use this
                # weaker compatibility view when the richer contract is available.
                if role == "systems_architect":
                    return [
                        {
                            "quality_score": 99,
                            "benefit_score": 0.99,
                            "runtime_status": "model_inference",
                        }
                    ][:limit]
                return []

        current_scores = [
            {
                "role": "source_mapper",
                "quality_score": 80,
                "benefit_score": 0.65,
                "unique_contribution": 0.70,
            },
            {
                "role": "adversarial_breaker",
                "quality_score": 82,
                "benefit_score": 0.66,
                "unique_contribution": 0.70,
            },
            {
                "role": "proof_engineer",
                "quality_score": 83,
                "benefit_score": 0.67,
                "unique_contribution": 0.72,
            },
            {
                "role": "systems_architect",
                "quality_score": 96,
                "benefit_score": 0.91,
                "unique_contribution": 0.90,
            },
            {
                "role": "innovation_inventor",
                "quality_score": 79,
                "benefit_score": 0.60,
                "unique_contribution": 0.78,
            },
        ]
        loop = ReceiptLineageSemanticClaimAdaptiveWorkerLoop(
            TEMPLATE_PATH,
            DualMemory(),
            min_workers=4,
            max_workers=8,
        )

        selected = loop._next_roles(current_scores, 4)
        telemetry = loop._last_worker_portfolio_selection

        self.assertEqual(selected[:3], MANDATORY)
        self.assertEqual(selected[3], "innovation_inventor")
        self.assertEqual(
            telemetry["history_source"],
            "RELIABILITY_CAUSAL_PORTFOLIO_MEMORY",
        )
        self.assertGreater(
            telemetry["signals"]["innovation_inventor"]["causal_bonus"],
            0.0,
        )
        self.assertGreater(
            telemetry["signals"]["systems_architect"]["failure_penalty"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
