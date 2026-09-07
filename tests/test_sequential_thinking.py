"""Tests for the Sequential Thinking Repository Enhancement Engine."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add root to sys.path so tools.sequential_thinking can be imported
ROOT_DIR = Path("/root")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sequential_thinking.anti_cookie_cutter import audit_enhancement_plan
from sequential_thinking.engine import SequentialSession, ThoughtPhase
from sequential_thinking.enhancer import generate_sequential_enhancement
from sequential_thinking.profiler import RepoProfile, profile_repository



class SequentialThinkingEngineTests(unittest.TestCase):
    def test_session_state_machine_and_branching(self) -> None:
        """Verify sequential thoughts, branching, revisions, and markdown export."""
        session = SequentialSession(topic="Test Mission", target_repo="/tmp/dummy")

        # Step 1: Deconstruct
        s1 = session.add_thought(
            phase=ThoughtPhase.DECONSTRUCT,
            hypothesis="Analyze baseline constraints",
            content="Discovered Python 3.14 environment with pytest harness.",
            receipt_criteria="Captured baseline",
        )
        self.assertEqual(s1.number, 1)
        self.assertEqual(s1.phase, ThoughtPhase.DECONSTRUCT)

        # Step 2: Branching
        session.branch("alt-architecture")
        s2 = session.add_thought(
            phase=ThoughtPhase.HYPOTHESIS,
            hypothesis="Explore alternative adapter branch",
            content="Testing isolated adapter instead of in-place mutation.",
            branch_id="alt-architecture",
        )
        self.assertEqual(s2.branch_id, "alt-architecture")
        self.assertIn("alt-architecture", session.branches)

        # Export check
        trace = session.export_trace()
        self.assertEqual(trace["total_steps"], 2)
        md = session.render_markdown()
        self.assertIn("Sequential Thinking Trace: Test Mission", md)
        self.assertIn("[alt-architecture]", md)

    def test_repo_profiler_on_real_repo(self) -> None:
        """Verify that profiler accurately extracts ground truth from real repos."""
        target = Path("/root/projects/monolith")
        profile = profile_repository(target, run_tests=False)

        self.assertEqual(profile.name, "monolith")
        self.assertIn("Python", profile.languages)
        self.assertTrue(profile.test_files_count > 0)
        self.assertIn("Meta-Layer Catalog", profile.archetype)
        self.assertTrue(len(profile.fingerprint) > 0)

        # Also test make-it-heavy build system detection
        mih_target = Path("/root/projects/make-it-heavy")
        mih_profile = profile_repository(mih_target, run_tests=False)
        self.assertIn("pyproject.toml", mih_profile.build_systems)
        self.assertIn("Python", mih_profile.languages)


    def test_anti_cookie_cutter_gate_rejects_boilerplate(self) -> None:
        """Verify that generic boilerplate and invariant breaches are rejected."""
        dummy_profile = RepoProfile(
            path="/tmp/dummy",
            name="mastermind",
            languages={"Python": 10},
            build_systems=["pyproject.toml"],
            test_framework="pytest",
            test_files_count=5,
            test_baseline={"status": "GREEN"},
            invariants=["ASYNC_ONLY_EVENT_LOOP", "APPEND_ONLY_RECEIPT_CHAIN"],
            archetype="Sovereign APEX Runtime & Identity",
            ast_hotspots=[],
            fingerprint="abc12345",
        )

        # 1. Banned generic boilerplate plan
        bad_plan = {
            "title": "Add generic helper wrapper",
            "description": "Boilerplate implementation of a generic adapter",
        }
        audit = audit_enhancement_plan(bad_plan, dummy_profile)
        self.assertFalse(audit["passed"])
        self.assertTrue(any("COOKIE_CUTTER_VIOLATION" in v for v in audit["violations"]))

        # 2. Invariant breach: blocking call in async repo
        blocking_plan = {
            "title": "Add network sync worker",
            "code": "time.sleep(5)",
        }
        audit2 = audit_enhancement_plan(blocking_plan, dummy_profile)
        self.assertFalse(audit2["passed"])
        self.assertTrue(any("ASYNC_ONLY_EVENT_LOOP" in v for v in audit2["violations"]))

    def test_end_to_end_enhancement_generation(self) -> None:
        """Verify that end-to-end sequential enhancement produces a bespoke, passing audit."""
        target = Path("/root/projects/monolith")
        result = generate_sequential_enhancement(target, run_tests=False)

        self.assertIn("profile", result)
        self.assertIn("trace", result)
        self.assertIn("markdown_report", result)
        self.assertIn("audit", result)

        self.assertEqual(len(result["trace"]["steps"]), 7)
        self.assertTrue(result["audit"]["passed"])
        self.assertGreaterEqual(result["audit"]["bespoke_score"], 0.3)


if __name__ == "__main__":
    unittest.main()
