import json
import tempfile
import unittest
from pathlib import Path

from worker_portfolio_cli import compile_worker_portfolio, main
from worker_portfolio_optimizer import select_worker_portfolio


class WorkerPortfolioOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.scores = [
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
                "quality_score": 88,
                "benefit_score": 0.78,
                "unique_contribution": 0.80,
            },
            {
                "role": "innovation_inventor",
                "quality_score": 79,
                "benefit_score": 0.60,
                "unique_contribution": 0.78,
            },
        ]
        self.roles = [row["role"] for row in self.scores]
        self.mandatory = ["source_mapper", "adversarial_breaker", "proof_engineer"]

    def test_without_history_preserves_mandatory_and_current_turn_strength(self):
        selected, _ = select_worker_portfolio(
            self.scores,
            next_count=4,
            candidate_roles=self.roles,
            mandatory_roles=self.mandatory,
        )
        self.assertEqual(selected[:3], self.mandatory)
        self.assertEqual(selected[3], "systems_architect")

    def test_longitudinal_failures_can_demote_flashy_current_turn(self):
        history = {
            role: [] for role in self.roles
        }
        history["systems_architect"] = [
            {
                "quality_score": 35,
                "benefit_score": 0.15,
                "unique_contribution": 0.20,
                "runtime_status": "model_inference",
            },
            {
                "quality_score": 0,
                "benefit_score": 0,
                "unique_contribution": 0,
                "runtime_status": "timeout",
                "performance_valid": False,
            },
            {
                "quality_score": 0,
                "benefit_score": 0,
                "unique_contribution": 0,
                "runtime_status": "error",
                "performance_valid": False,
            },
        ]
        history["innovation_inventor"] = [
            {
                "quality_score": 86,
                "benefit_score": 0.76,
                "unique_contribution": 0.82,
                "runtime_status": "model_inference",
            },
            {
                "quality_score": 84,
                "benefit_score": 0.74,
                "unique_contribution": 0.80,
                "runtime_status": "model_inference",
            },
        ]

        def provider(role, limit):
            return history[role][:limit]

        selected, signals = select_worker_portfolio(
            self.scores,
            next_count=4,
            candidate_roles=self.roles,
            mandatory_roles=self.mandatory,
            history_provider=provider,
        )
        self.assertEqual(selected[3], "innovation_inventor")
        self.assertGreater(
            signals["systems_architect"].failure_penalty,
            signals["innovation_inventor"].failure_penalty,
        )

    def test_sparse_history_gets_bounded_exploration_without_displacing_mandatory(self):
        history = {role: [] for role in self.roles}
        history["systems_architect"] = [
            {
                "quality_score": 86,
                "benefit_score": 0.75,
                "unique_contribution": 0.75,
                "runtime_status": "model_inference",
            }
            for _ in range(8)
        ]
        history["innovation_inventor"] = []

        def provider(role, limit):
            return history[role][:limit]

        selected, signals = select_worker_portfolio(
            self.scores,
            next_count=4,
            candidate_roles=self.roles,
            mandatory_roles=self.mandatory,
            history_provider=provider,
        )
        self.assertEqual(selected[:3], self.mandatory)
        self.assertLessEqual(signals["innovation_inventor"].exploration_bonus, 0.22)
        self.assertGreater(
            signals["innovation_inventor"].exploration_bonus,
            signals["systems_architect"].exploration_bonus,
        )

    def test_explicit_causal_evidence_changes_signal_without_inventing_it(self):
        no_causal = {
            "quality_score": 80,
            "benefit_score": 0.65,
            "unique_contribution": 0.70,
            "runtime_status": "model_inference",
            "marginal_system_value": None,
            "outcome_leverage": None,
        }
        causal = dict(no_causal)
        causal["marginal_system_value"] = 0.40
        causal["outcome_leverage"] = 0.80
        history = {role: [] for role in self.roles}
        history["systems_architect"] = [causal]
        history["innovation_inventor"] = [no_causal]

        def provider(role, limit):
            return history[role][:limit]

        _, signals = select_worker_portfolio(
            self.scores,
            next_count=4,
            candidate_roles=self.roles,
            mandatory_roles=self.mandatory,
            history_provider=provider,
        )
        self.assertGreater(signals["systems_architect"].causal_bonus, 0)
        self.assertEqual(signals["innovation_inventor"].causal_bonus, 0)

    def test_cli_emits_deterministic_receipt(self):
        payload = {
            "scores": self.scores,
            "candidate_roles": self.roles,
            "mandatory_roles": self.mandatory,
            "next_count": 4,
            "history": {role: [] for role in self.roles},
        }
        first = compile_worker_portfolio(payload)
        second = compile_worker_portfolio(payload)
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "glaciereq.make-it-heavy.worker-portfolio.v1")
        self.assertEqual(first["selected_roles"][:3], self.mandatory)

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "input.json"
            output = Path(temp_dir) / "receipt.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(main([str(source), "--output", str(output)]), 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(receipt, first)

    def test_invalid_capacity_fails_closed(self):
        with self.assertRaises(ValueError):
            select_worker_portfolio(
                self.scores,
                next_count=99,
                candidate_roles=self.roles,
                mandatory_roles=self.mandatory,
            )


if __name__ == "__main__":
    unittest.main()
