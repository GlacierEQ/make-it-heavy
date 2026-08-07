"""Regression tests for Turn-6 live source-span semantic gating."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claim_aware_innovation import ClaimAwareAdaptiveWorkerLoop
from immutable_span_resolver import (
    LocalGitImmutableSpanResolver,
    SPAN_GIT_TIMEOUT,
    SPAN_PATH_UNSAFE,
    SPAN_RESOLVED,
    StaticSpanResolver,
)
from semantic_support import (
    SOURCE_CONTRADICTS_CLAIM,
    SOURCE_ENTAILS_CLAIM,
    SOURCE_INSUFFICIENT,
    evaluate_source_span_support,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "innovation_workers.yaml"
REVISION = "a" * 40


def mission() -> str:
    return f"""
Evaluate the exact evidence span.
EVIDENCE_REGISTRY_BEGIN
{{"S1": {{"E1": "evidence.txt@{REVISION}#L1-L3"}}}}
EVIDENCE_REGISTRY_END
""".strip()


def source_mapper_response(observed: str) -> str:
    return f"""
SOURCES
OBSERVED[S1#E1]: {observed}
SUPPORTED OBSERVATIONS
INFERENCE: The bounded observation may inform the next implementation step.
CONTRADICTIONS OR GAPS
BLOCKED: External-world correctness beyond this span remains unverified.
HANDOFF
PROPOSED: Preserve the semantic receipt and run the next deterministic test.
""".strip()


class SemanticEvaluatorHardeningTests(unittest.TestCase):
    def test_unrelated_negation_does_not_create_false_contradiction(self) -> None:
        result = evaluate_source_span_support(
            "The provider status is verified.",
            "The worker does not mutate files. The provider status is verified.",
            "S1#E1",
        )
        self.assertEqual(result.relation, SOURCE_ENTAILS_CLAIM)

    def test_clause_local_negation_is_a_contradiction(self) -> None:
        result = evaluate_source_span_support(
            "The provider status is verified.",
            "The provider status is not verified.",
            "S1#E1",
        )
        self.assertEqual(result.relation, SOURCE_CONTRADICTS_CLAIM)

    def test_sentence_case_word_is_not_promoted_to_technical_identifier(self) -> None:
        result = evaluate_source_span_support(
            "OpenAI model is enabled.",
            "OpenAI model is enabled.",
            "S1#E1",
        )
        self.assertEqual(result.relation, SOURCE_ENTAILS_CLAIM)
        self.assertEqual(result.unsupported_identifiers, ())

    def test_new_identifier_precision_fails_closed(self) -> None:
        result = evaluate_source_span_support(
            "The command uses --verify.",
            "The command validates the commit.",
            "S1#E1",
        )
        self.assertEqual(result.relation, SOURCE_INSUFFICIENT)
        self.assertIn("--verify", result.unsupported_identifiers)


class ImmutableSpanResolverTests(unittest.TestCase):
    def test_local_git_resolver_reads_exact_committed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "turn6@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Turn 6"], cwd=root, check=True
            )
            (root / "evidence.txt").write_text(
                "alpha\nbeta\ngamma\ndelta\n", encoding="utf-8"
            )
            subprocess.run(["git", "add", "evidence.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()

            resolution = LocalGitImmutableSpanResolver(root).resolve(
                "S1#E1", f"evidence.txt@{revision}#L2-L3"
            )

            self.assertEqual(resolution.state, SPAN_RESOLVED)
            self.assertEqual(resolution.span_text, "beta\ngamma")
            self.assertEqual(len(resolution.span_sha256), 64)

    def test_resolver_rejects_path_traversal_before_git_access(self) -> None:
        resolution = LocalGitImmutableSpanResolver(ROOT).resolve(
            "S1#E1", f"../secret.txt@{REVISION}#L1"
        )
        self.assertEqual(resolution.state, SPAN_PATH_UNSAFE)

    def test_git_timeout_becomes_structured_resolution_state(self) -> None:
        resolver = LocalGitImmutableSpanResolver(ROOT, timeout=0.5)
        with patch(
            "immutable_span_resolver.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=0.5),
        ):
            resolution = resolver.resolve(
                "S1#E1", f"evidence.txt@{REVISION}#L1-L3"
            )

        self.assertEqual(resolution.state, SPAN_GIT_TIMEOUT)
        self.assertFalse(resolution.resolved)
        self.assertIn("timed out", resolution.error.lower())


class RuntimeSemanticGateTests(unittest.TestCase):
    def _loop(self, spans: dict[str, str]) -> ClaimAwareAdaptiveWorkerLoop:
        return ClaimAwareAdaptiveWorkerLoop(
            TEMPLATES,
            span_resolver=StaticSpanResolver(spans),
        )

    def _score(self, loop: ClaimAwareAdaptiveWorkerLoop, observed: str):
        loop.build_subtasks(mission(), [{"role": "source_mapper"}])
        template = loop.template_for_role("source_mapper")
        assert template is not None
        return loop._score_one(
            template,
            {
                "agent_id": 0,
                "role": "source_mapper",
                "model": "fixture-model",
                "status": "model_inference",
                "response": source_mapper_response(observed),
                "execution_time": 1.0,
            },
            novelty=1.0,
            peers=[],
        )

    def test_supported_span_passes_live_semantic_gate(self) -> None:
        loop = self._loop({"S1#E1": "The provider status is verified."})
        score = self._score(loop, "The provider status is verified.")

        self.assertTrue(score["claim_gate"]["pass"])
        self.assertTrue(score["semantic_gate"]["pass"])
        self.assertEqual(
            score["semantic_gate"]["semantic_support_status"], "SOURCE_SUPPORT_PASS"
        )

    def test_contradicted_span_fails_and_tightens_semantics(self) -> None:
        loop = self._loop({"S1#E1": "The provider status is not verified."})
        score = self._score(loop, "The provider status is verified.")
        adjustment = loop._adjustment(score)

        self.assertTrue(score["claim_gate"]["pass"])
        self.assertFalse(score["semantic_gate"]["pass"])
        self.assertEqual(score["semantic_gate"]["failure_class"], "CLAIM_SEMANTICS")
        self.assertLessEqual(score["quality_score"], 69.0)
        self.assertEqual(adjustment["action"], "TIGHTEN_SEMANTIC_SUPPORT")

    def test_unavailable_span_holds_template_and_repairs_evidence(self) -> None:
        loop = self._loop({})
        score = self._score(loop, "The provider status is verified.")
        adjustment = loop._adjustment(score)

        self.assertFalse(score["semantic_gate"]["pass"])
        self.assertEqual(
            score["semantic_gate"]["failure_class"], "EVIDENCE_RESOLUTION"
        )
        self.assertEqual(adjustment["action"], "HOLD_TEMPLATE_REPAIR_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
