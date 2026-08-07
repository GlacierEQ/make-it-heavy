import hashlib
import unittest
from pathlib import Path

from hydrated_claim_innovation import (
    HYDRATED_EVIDENCE_BEGIN,
    HydratedClaimAwareAdaptiveWorkerLoop,
)
from immutable_span_resolver import StaticSpanResolver


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "innovation_workers.yaml"
REVISION = "a" * 40
LOCATOR = f"src/example.py@{REVISION}#L1-L2"
SPAN = (
    'process = subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"], '
    'check=False); if process.returncode != 0: return None'
)


def mission(locator: str = LOCATOR) -> str:
    return f'''Inspect one immutable claim.
EVIDENCE_REGISTRY_BEGIN
{{"S1":{{"E1":"{locator}"}}}}
EVIDENCE_REGISTRY_END
'''


class EvidenceHydrationTests(unittest.TestCase):
    def make_loop(self, spans, budget=16000):
        return HydratedClaimAwareAdaptiveWorkerLoop(
            TEMPLATE_PATH,
            memory=None,
            min_workers=4,
            max_workers=8,
            span_resolver=StaticSpanResolver(spans),
            prompt_evidence_budget_chars=budget,
        )

    def test_exact_span_bytes_are_hydrated_before_generation_and_reused(self):
        loop = self.make_loop({"S1#E1": SPAN})
        task = loop.build_subtasks(
            mission(),
            [{"role": "source_mapper", "model": "test-model"}],
        )[0]

        self.assertIn(HYDRATED_EVIDENCE_BEGIN, task)
        self.assertIn(SPAN, task)
        self.assertIn(hashlib.sha256(SPAN.encode()).hexdigest(), task)
        self.assertEqual(loop._hydrated_span_text_by_pointer["S1#E1"], SPAN)

        response = (
            "OBSERVED[S1#E1]: The resolver runs git rev-parse --verify "
            "HEAD^{commit} and returns None when commit resolution fails."
        )
        semantic = loop.evaluate_semantic_support(response)
        self.assertTrue(semantic["pass"], semantic)
        self.assertTrue(semantic["same_bytes_generation_and_scoring"])
        self.assertEqual(semantic["prompt_available_span_count"], 1)
        self.assertEqual(semantic["resolved_span_count"], 1)

    def test_broad_claim_still_fails_after_hydration(self):
        loop = self.make_loop({"S1#E1": SPAN})
        loop.build_subtasks(
            mission(),
            [{"role": "source_mapper", "model": "test-model"}],
        )
        semantic = loop.evaluate_semantic_support(
            "OBSERVED[S1#E1]: The resolver is complete and production-ready."
        )
        self.assertFalse(semantic["pass"])
        self.assertEqual(semantic["failure_class"], "CLAIM_SEMANTICS")

    def test_budget_omitted_span_is_not_available_to_generation_or_scoring(self):
        large_span = "supported_fact = True\n" + ("x = 'evidence'\n" * 200)
        loop = self.make_loop({"S1#E1": large_span}, budget=1000)
        task = loop.build_subtasks(
            mission(),
            [{"role": "source_mapper", "model": "test-model"}],
        )[0]

        self.assertNotIn(large_span, task)
        self.assertNotIn("S1#E1", loop._hydrated_span_text_by_pointer)
        self.assertEqual(
            loop._hydration_receipts[0]["prompt_omission_reason"],
            "PROMPT_EVIDENCE_BUDGET_EXCEEDED",
        )
        semantic = loop.evaluate_semantic_support(
            "OBSERVED[S1#E1]: supported_fact is true."
        )
        self.assertFalse(semantic["pass"])
        self.assertEqual(
            semantic["failure_class"],
            "EVIDENCE_PROMPT_AVAILABILITY",
        )

    def test_unresolved_span_is_marked_unavailable_before_generation(self):
        loop = self.make_loop({})
        task = loop.build_subtasks(
            mission(),
            [{"role": "source_mapper", "model": "test-model"}],
        )[0]

        self.assertIn(HYDRATED_EVIDENCE_BEGIN, task)
        self.assertFalse(loop._hydration_receipts[0]["prompt_available"])
        self.assertEqual(
            loop._hydration_receipts[0]["prompt_omission_reason"],
            "SPAN_PATH_UNAVAILABLE",
        )

    def test_no_registry_preserves_legacy_prompt_shape(self):
        loop = self.make_loop({})
        task = loop.build_subtasks(
            "General innovation mission without an evidence registry.",
            [{"role": "source_mapper", "model": "test-model"}],
        )[0]
        self.assertNotIn(HYDRATED_EVIDENCE_BEGIN, task)


if __name__ == "__main__":
    unittest.main()
