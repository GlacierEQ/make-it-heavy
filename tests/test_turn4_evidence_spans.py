"""Regression tests for Turn-4 immutable evidence-span gating."""

from __future__ import annotations

from pathlib import Path
import unittest

from claim_aware_innovation import (
    ClaimAwareAdaptiveWorkerLoop,
    InnovationConfigurationError,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "innovation_workers.yaml"
REVISION = "a" * 40


def mission_with_registry(locator: str | None = None) -> str:
    evidence_locator = locator or f"scripts/example.py@{REVISION}#L10-L20"
    return f"""
Inspect the proof slice and preserve exact evidence identity.

EVIDENCE_REGISTRY_BEGIN
{{"S1": {{"E1": "{evidence_locator}"}}}}
EVIDENCE_REGISTRY_END
""".strip()


class EvidenceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = ClaimAwareAdaptiveWorkerLoop(TEMPLATES)

    def test_valid_registry_parses_immutable_span(self) -> None:
        registry = self.loop.parse_evidence_registry(mission_with_registry())

        self.assertEqual(
            registry,
            {"S1": {"E1": f"scripts/example.py@{REVISION}#L10-L20"}},
        )

    def test_malformed_registry_fails_closed(self) -> None:
        with self.assertRaises(InnovationConfigurationError):
            self.loop.parse_evidence_registry(
                "EVIDENCE_REGISTRY_BEGIN\n{not-json}\nEVIDENCE_REGISTRY_END"
            )

    def test_duplicate_registry_markers_fail_closed(self) -> None:
        mission = (
            mission_with_registry()
            + "\nEVIDENCE_REGISTRY_BEGIN\n"
            + '{"S2":{"E1":"scripts/other.py@' + REVISION + '#L1"}}\n'
            + "EVIDENCE_REGISTRY_END"
        )
        with self.assertRaisesRegex(
            InnovationConfigurationError, "exactly one begin marker"
        ):
            self.loop.parse_evidence_registry(mission)

    def test_mutable_revision_is_rejected(self) -> None:
        with self.assertRaises(InnovationConfigurationError):
            self.loop.parse_evidence_registry(
                mission_with_registry("scripts/example.py@main#L10-L20")
            )

    def test_registered_observed_pointer_passes_but_entailment_stays_unchecked(self) -> None:
        self.loop.build_subtasks(
            mission_with_registry(),
            [{"role": "source_mapper"}],
        )
        response = """
OBSERVED[S1#E1]: The supplied span contains the directly quoted source observation.
INFERENCE: The observation may imply a reusable verification boundary.
PROPOSED: Add one deterministic proof receipt.
BLOCKED: Semantic correctness beyond the cited span is not established here.
"""

        gate = self.loop.evaluate_claim_discipline(response)

        self.assertTrue(gate["pass"])
        self.assertTrue(gate["evidence_registry_active"])
        self.assertEqual(gate["source_pointer_status"], "SOURCE_POINTER_RESOLVED")
        self.assertEqual(gate["resolved_pointer_count"], 1)
        self.assertEqual(gate["semantic_support_status"], "SOURCE_SUPPORT_UNCHECKED")
        self.assertEqual(gate["semantic_support_unchecked_count"], 1)

    def test_source_only_observed_claim_fails_when_registry_is_active(self) -> None:
        self.loop.build_subtasks(
            mission_with_registry(),
            [{"role": "source_mapper"}],
        )
        response = """
OBSERVED[S1]: The claim names a source but omits the registered evidence span.
INFERENCE: This should fail closed under Turn 4.
PROPOSED: Require the exact span id.
BLOCKED: No semantic verdict is available.
"""

        gate = self.loop.evaluate_claim_discipline(response)

        self.assertFalse(gate["pass"])
        self.assertEqual(gate["source_pointer_status"], "SOURCE_POINTER_INVALID")
        self.assertEqual(gate["invalid_observed_reference_count"], 1)
        self.assertLess(gate["score"], 1.0)

    def test_unknown_source_or_span_fails_pointer_gate_and_source_score(self) -> None:
        self.loop.build_subtasks(
            mission_with_registry(),
            [{"role": "source_mapper"}],
        )
        for reference in ("S2#E1", "S1#E9"):
            with self.subTest(reference=reference):
                gate = self.loop.evaluate_claim_discipline(
                    f"""
OBSERVED[{reference}]: This pointer is not registered.
INFERENCE: It must not be treated as proof.
PROPOSED: Use only registered pointers.
BLOCKED: The claimed observation is unavailable.
"""
                )
                self.assertFalse(gate["pass"])
                self.assertEqual(
                    gate["source_pointer_status"],
                    "SOURCE_POINTER_INVALID",
                )
                self.assertLess(gate["score"], 1.0)

    def test_legacy_source_id_mode_remains_backward_compatible(self) -> None:
        response = """
OBSERVED[baseline-zero]: The supplied source records the worker topology.
INFERENCE: The topology may contain redundant coverage.
PROPOSED: Test a smaller topology.
BLOCKED: Employer adoption is not established.
"""

        gate = self.loop.evaluate_claim_discipline(response, {})

        self.assertTrue(gate["pass"])
        self.assertFalse(gate["evidence_registry_active"])
        self.assertEqual(gate["source_pointer_status"], "LEGACY_SOURCE_ID_MODE")

    def test_invalid_legacy_observed_source_fails_hard_gate(self) -> None:
        response = """
OBSERVED[unknown#invented]: This reference is not a valid legacy source id.
INFERENCE: The observation is unsupported.
PROPOSED: Use a real source id.
BLOCKED: Direct support is unavailable.
"""

        gate = self.loop.evaluate_claim_discipline(response, {})

        self.assertFalse(gate["pass"])
        self.assertEqual(gate["invalid_observed_reference_count"], 1)
        self.assertIn("unknown#invented", gate["invalid_observed_references"])

    def test_invalid_pointer_caps_score_and_emits_pointer_specific_adjustment(self) -> None:
        template = self.loop.template_for_role("source_mapper")
        assert template is not None
        self.loop.build_subtasks(
            mission_with_registry(),
            [{"role": "source_mapper"}],
        )
        response = """
SOURCES
OBSERVED[S1]: Source identity is named without the required registered span.
SUPPORTED OBSERVATIONS
INFERENCE: The source-only citation is insufficient under the active registry.
CONTRADICTIONS OR GAPS
BLOCKED: Exact direct support is not established by this pointer.
HANDOFF
PROPOSED: Retry with OBSERVED[S1#E1].
"""
        score = self.loop._score_one(
            template,
            {
                "agent_id": 0,
                "role": "source_mapper",
                "model": "test-model",
                "status": "model_inference",
                "response": response,
                "execution_time": 1.0,
            },
            novelty=1.0,
            peers=[],
        )
        adjustment = self.loop._adjustment(score)

        self.assertFalse(score["claim_gate"]["pass"])
        self.assertLessEqual(score["quality_score"], 69.0)
        self.assertEqual(adjustment["action"], "TIGHTEN_SOURCE_POINTERS")

    def test_worker_task_explains_pointer_identity_is_not_entailment(self) -> None:
        tasks = self.loop.build_subtasks(
            mission_with_registry(),
            [{"role": "source_mapper"}],
        )

        self.assertEqual(len(tasks), 1)
        self.assertIn("OBSERVED[source-id#span-id]", tasks[0])
        self.assertIn("does NOT by itself prove semantic entailment", tasks[0])


if __name__ == "__main__":
    unittest.main()
