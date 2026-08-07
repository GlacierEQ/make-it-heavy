import unittest
from pathlib import Path

from semantic_claim_firewall import evaluate_semantic_claim_firewall
from semantic_claim_innovation import (
    SEMANTIC_CLAIM_CONTRACT,
    SemanticClaimAdaptiveWorkerLoop,
)
from semantic_support import (
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"
SOURCE_SPAN = (
    'process = subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"], '
    'cwd=cwd, check=False); if process.returncode != 0: return None'
)


class SemanticClaimFirewallTests(unittest.TestCase):
    def test_atomic_source_supported_claim_passes(self):
        response = (
            "OBSERVED[S1#E1]: The resolver runs git rev-parse --verify "
            "HEAD^{commit} and returns None when commit resolution fails."
        )
        result = evaluate_semantic_claim_firewall(
            response,
            {"S1#E1": SOURCE_SPAN},
        )
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(
            result["relation_counts"][SOURCE_ENTAILS_CLAIM],
            1,
        )

    def test_broad_observed_claim_is_quarantined(self):
        response = "OBSERVED[S1#E1]: The resolver is complete and production-ready."
        result = evaluate_semantic_claim_firewall(
            response,
            {"S1#E1": SOURCE_SPAN},
        )
        self.assertFalse(result["pass"])
        self.assertEqual(result["adjustment"], "NARROW_OBSERVED_TO_SPAN")
        self.assertEqual(
            result["relation_counts"][SOURCE_INSUFFICIENT],
            1,
        )

    def test_explicit_state_conflict_escalates(self):
        response = "OBSERVED[S2#E1]: identity status is RESOLVED."
        result = evaluate_semantic_claim_firewall(
            response,
            {"S2#E1": "identity status is UNRESOLVED"},
        )
        self.assertFalse(result["pass"])
        self.assertEqual(result["adjustment"], "ESCALATE_CONTRADICTION")
        self.assertEqual(
            result["relation_counts"][SOURCE_CONTRADICTS_CLAIM],
            1,
        )

    def test_missing_exact_span_fails_closed(self):
        response = "OBSERVED[S9#E9]: a claim with a valid-looking pointer."
        result = evaluate_semantic_claim_firewall(response, {})
        self.assertFalse(result["pass"])
        self.assertEqual(result["adjustment"], "FIX_SEMANTIC_POINTER")
        self.assertEqual(result["missing_pointer_count"], 1)

    def test_semantic_adaptive_loop_appends_hard_gate_and_adjusts(self):
        loop = SemanticClaimAdaptiveWorkerLoop(
            TEMPLATE_PATH,
            memory=None,
            min_workers=4,
            max_workers=8,
        )
        mission = """Audit one claim.
EVIDENCE_REGISTRY_BEGIN
{"S1":{"E1":"src/file.py@0123456789012345678901234567890123456789#L1-L4"}}
EVIDENCE_REGISTRY_END
SEMANTIC_SPAN_REGISTRY_BEGIN
{"S1#E1":"process runs git rev-parse --verify HEAD^{commit} and returns None on failure"}
SEMANTIC_SPAN_REGISTRY_END
"""
        profile = {"role": "source_mapper", "model": "test-model"}
        task = loop.build_subtasks(mission, [profile])[0]
        self.assertIn(SEMANTIC_CLAIM_CONTRACT, task)

        response = """## SOURCE LEDGER
OBSERVED[S1#E1]: The resolver is production-ready.
## BINDING CONSTRAINT
INFERENCE: Broader correctness is not established.
## CONTRADICTIONS
BLOCKED: None tested.
## HANDOFF
PROPOSED: Narrow the observed claim.
"""
        result = {
            "agent_id": 0,
            "role": "source_mapper",
            "model": "test-model",
            "status": "model_inference",
            "response": response,
            "execution_time": 1.0,
        }
        score = loop._score_one(
            loop.templates_by_role["source_mapper"],
            result,
            1.0,
            [],
        )
        self.assertFalse(score["semantic_claim_gate"]["pass"])
        self.assertLessEqual(score["quality_score"], 59.0)
        adjustment = loop._adjustment(score)
        self.assertEqual(adjustment["action"], "NARROW_OBSERVED_TO_SPAN")


if __name__ == "__main__":
    unittest.main()
