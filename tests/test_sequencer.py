"""
Tests for the Sequencer — profile, plan, gate, and pattern coverage.

These are the test file the make-it-heavy AGENTS.md rule requires
("no tool merges without a test"). They also pin the anti-cookie-cutter
behaviour so a future edit can't silently disable it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path("/root/projects/make-it-heavy")
sys.path.insert(0, str(REPO_ROOT))

from make_it_heavy.sequencer.discover import build_profile  # noqa: E402
from make_it_heavy.sequencer.gate import check, _record_only  # noqa: E402
from make_it_heavy.sequencer.patterns import all_patterns  # noqa: E402
from make_it_heavy.sequencer.plan import build_plan  # noqa: E402


class TestPatternCatalog(unittest.TestCase):
    def test_every_pattern_declares_when_profile(self):
        """A pattern that always fires is a template, not an enhancement."""
        for p in all_patterns():
            self.assertTrue(
                len(p.when_profile) > 0,
                f"{p.id} has no when_profile — would always fire (template)",
            )

    def test_every_pattern_has_a_differentiator(self):
        """The differentiator is the human-language proof of non-templating."""
        for p in all_patterns():
            self.assertTrue(
                len(p.differentiator) > 20,
                f"{p.id} differentiator is too short to be a real differentiator",
            )

    def test_pattern_ids_are_unique(self):
        ids = [p.id for p in all_patterns()]
        self.assertEqual(len(ids), len(set(ids)), "duplicate pattern id")


class TestProfile(unittest.TestCase):
    def test_token_saver_profile_signals_match_known_truth(self):
        """Pin the live profile against the work we just did. If a future
        edit to the discoverer changes the signal set silently, this test
        fires and we re-check the patterns."""
        profile = build_profile("/root/projects/mermicorn/token-saver")
        s = profile.signals
        self.assertTrue(s["has_python_src"])
        self.assertTrue(s["has_module_init"])
        # Token-saver had no __main__ before our reconstruction.
        self.assertFalse(s["no_main_module"])  # we added it
        self.assertEqual(s["test_framework"], "pytest")
        self.assertTrue(s["test_count"] >= 230)  # 228 baseline + our additions
        self.assertTrue(s["has_persistent_state"])
        self.assertTrue(s["has_log_path"])
        self.assertFalse(s["log_file_empty"])  # we wrote to it in the smoke
        self.assertTrue(s["has_user_docs"])
        self.assertTrue(s["sibling_has_meta_catalog"])

    def test_monolith_self_detects_as_catalog(self):
        profile = build_profile("/root/projects/monolith")
        self.assertTrue(profile.signals["sibling_has_meta_catalog"])


class TestPlanIsPerRepoUnique(unittest.TestCase):
    """The core anti-cookie-cutter guarantee: the same patterns must NOT
    fire on every repo. Build plans from hand-crafted profiles (no
    filesystem I/O) so this test stays fast."""

    def test_three_profiles_three_different_proposal_sets(self):
        from make_it_heavy.sequencer.discover import Profile
        # Three very different profiles — exercise the matcher's branches.
        profiles = [
            Profile(path="/fake/a", name="a", signals={
                "has_python_src": True, "has_module_init": True,
            }),
            Profile(path="/fake/b", name="b", signals={
                "has_python_src": True, "has_persistent_state": True,
                "no_main_module": True,
            }),
            Profile(path="/fake/c", name="c", signals={
                "sibling_has_meta_catalog": True, "not_in_catalog": True,
                "has_python_src": True,
            }),
        ]
        plans = [build_plan(p) for p in profiles]
        sigs = [frozenset(pl.pattern.id for pl in pln.proposals) for pln in plans]
        unique = len(set(sigs))
        self.assertGreaterEqual(unique, 2, (
            f"only {unique} unique plan signatures across 3 profiles — "
            "the sequencer is templating"
        ))
        # And concretely, every plan must differ in at least one proposal.
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                self.assertNotEqual(sigs[i], sigs[j],
                                    f"plan {i} and plan {j} are identical")


class TestGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._old_path = os.environ.get("SEQUENCER_HISTORY_PATH")
        # Redirect the history file so the test doesn't touch the real one.
        os.environ["SEQUENCER_HISTORY_PATH"] = os.path.join(self._tmp, "history.json")

    def tearDown(self):
        if self._old_path is not None:
            os.environ["SEQUENCER_HISTORY_PATH"] = self._old_path
        else:
            os.environ.pop("SEQUENCER_HISTORY_PATH", None)

    def test_first_run_passes_second_run_warns(self):
        # Re-route the gate module's history path to the tmp dir.
        import make_it_heavy.sequencer.gate as gate_mod
        gate_mod.HISTORY_PATH = Path(os.environ["SEQUENCER_HISTORY_PATH"])

        profile = build_profile("/root/projects/mermicorn/token-saver")
        plan = build_plan(profile)
        first = check(plan)
        self.assertTrue(first.passed, f"first run should pass, got {first.reasons}")

        # Second run on the same plan: gate must warn.
        second = check(plan)
        self.assertFalse(second.passed)
        self.assertGreater(second.overlap_with_previous, 0.6)
        self.assertTrue(
            any("overlap" in r.lower() for r in second.reasons),
            f"expected an overlap warning, got: {second.reasons}",
        )

    def test_different_produces_different_digest(self):
        import make_it_heavy.sequencer.gate as gate_mod
        gate_mod.HISTORY_PATH = Path(os.environ["SEQUENCER_HISTORY_PATH"])

        # Two structurally different profiles, plans, and digests.
        from make_it_heavy.sequencer.discover import Profile
        p1 = Profile(path="/fake/a", name="a", signals={"has_python_src": True, "has_module_init": True})
        p2 = Profile(path="/fake/b", name="b", signals={"sibling_has_meta_catalog": True, "not_in_catalog": True})
        plan1 = build_plan(p1)
        plan2 = build_plan(p2)
        d1 = gate_mod._digest(plan1)
        d2 = gate_mod._digest(plan2)
        self.assertNotEqual(d1["matched_signals"], d2["matched_signals"])


class TestCliEndToEnd(unittest.TestCase):
    def test_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "make_it_heavy.sequencer", "--help"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("discover", proc.stdout)
        self.assertIn("plan", proc.stdout)
        self.assertIn("gate", proc.stdout)
        self.assertIn("demo", proc.stdout)

    def test_discover_returns_json(self):
        proc = subprocess.run(
            [sys.executable, "-m", "make_it_heavy.sequencer",
             "discover", "/root/projects/mermicorn/token-saver"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["name"], "token-saver")
        self.assertIn("signals", doc)
        self.assertIn("has_python_src", doc["signals"])


if __name__ == "__main__":
    unittest.main()
