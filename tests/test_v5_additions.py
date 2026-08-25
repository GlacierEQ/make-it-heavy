# SPDX-License-Identifier: Proprietary
"""Tests for the v5.0 additions: genius engine, local tier, run-state, batch."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from make_it_heavy.genius_orchestration import (
    GeniusOrchestrator,
    GeniusOrchestrationConfig,
)
from local_agent import LocalAgent, LocalAgentError
from make_it_heavy.run_state import RunStateStore, list_runs, PHASE_ORDER
from make_it_heavy.batch import run as batch_run
from semantic_claim_firewall import evaluate_semantic_claim_firewall


def make_local_agent_proxy():
    from local_agent import make_local_agent
    try:
        return make_local_agent(config_path="config.yaml")
    except Exception:
        return None


class SemanticFirewallTests(unittest.TestCase):
    def _src(self):
        return {"CASE-001": "TRO 515 issued Oct 3 2024 based on fraudulent HPD report"}

    def test_entailed_claim_passes(self):
        r = evaluate_semantic_claim_firewall(
            "OBSERVED[CASE-001]: TRO 515 issued Oct 3 2024 based on fraudulent HPD report",
            self._src(),
        )
        self.assertTrue(r["pass"])
        self.assertEqual(r["score"], 1.0)
        self.assertEqual(r["adjustment"], "KEEP_SEMANTIC_DISCIPLINE")

    def test_contradicted_claim_fails_closed(self):
        r = evaluate_semantic_claim_firewall(
            "OBSERVED[CASE-001]: TRO 515 was never issued", self._src()
        )
        self.assertFalse(r["pass"])
        self.assertEqual(r["adjustment"], "ESCALATE_CONTRADICTION")

    def test_missing_pointer_fails_closed(self):
        r = evaluate_semantic_claim_firewall("OBSERVED[NOPTR]: something", self._src())
        self.assertFalse(r["pass"])
        self.assertEqual(r["adjustment"], "FIX_SEMANTIC_POINTER")

    def test_no_observed_claims_is_not_applicable(self):
        r = evaluate_semantic_claim_firewall("nothing here", self._src())
        self.assertFalse(r["applicable"])
        # With require_observed=True (default), no observed claims means the
        # gate is not applicable and the run fails closed.
        self.assertFalse(r["pass"])
        self.assertEqual(r["adjustment"], "ADD_ATOMIC_OBSERVED_CLAIM")

    def test_no_observed_claims_passes_when_not_required(self):
        r = evaluate_semantic_claim_firewall(
            "nothing here", self._src(), require_observed=False
        )
        self.assertFalse(r["applicable"])
        self.assertTrue(r["pass"])


class GeniusOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmp, "config.yaml")
        Path(self.cfg_path).write_text(
            "openrouter:\n  api_key: test\n  base_url: https://example.invalid\n  model: openai/gpt-4.1-mini\n"
            "orchestrator:\n  parallel_agents: 4\n  task_timeout: 60\n  aggregation_strategy: consensus\n"
            "  question_generation_prompt: 'x'\n  synthesis_prompt: 'y'\n"
            "system_prompt: 's'\n"
            "apex_agents:\n"
            "  - role: source_researcher\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: claim_auditor\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: counter_analyst\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: review_planner\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
        )

    def test_decompose_covers_all_roles(self):
        cfg = GeniusOrchestrationConfig(goal="test goal")
        eng = GeniusOrchestrator(cfg, config_path=self.cfg_path)
        subs = eng._decompose("test goal")
        self.assertEqual(len(subs), 4)
        self.assertTrue(all("OBSERVED[" in s for s in subs))

    def test_quality_gate_fails_closed_on_firewall(self):
        cfg = GeniusOrchestrationConfig(
            goal="g",
            source_registry={"CASE-001": "TRO 515 issued Oct 3 2024"},
        )
        eng = GeniusOrchestrator(cfg, config_path=self.cfg_path)
        fw = {
            "pass": False,
            "adjustment": "FIX_SEMANTIC_POINTER",
            "observed_claim_count": 1,
            "score": 0.0,
        }
        self.assertFalse(eng._apply_quality_gates("result", fw))

    def test_quality_gate_passes_when_firewall_ok(self):
        cfg = GeniusOrchestrationConfig(goal="g", source_registry={"CASE-001": "x"})
        eng = GeniusOrchestrator(cfg, config_path=self.cfg_path)
        fw = {"pass": True, "adjustment": "KEEP_SEMANTIC_DISCIPLINE",
              "observed_claim_count": 1, "score": 1.0}
        self.assertTrue(eng._apply_quality_gates("result", fw))

    def test_record_receipt_has_sha(self):
        cfg = GeniusOrchestrationConfig(goal="g")
        eng = GeniusOrchestrator(cfg, config_path=self.cfg_path)
        fw = {"pass": True, "score": 1.0, "observed_claim_count": 0,
              "adjustment": "KEEP_SEMANTIC_DISCIPLINE"}
        r = eng._record_receipt(1, "synthesis text", fw)
        self.assertEqual(r["schema"], "glaciereq.make-it-heavy.genius-receipt.v1")
        self.assertEqual(r["iteration"], 1)
        self.assertTrue(r["firewall_pass"])


class LocalAgentTests(unittest.TestCase):
    def test_disabled_agent_unavailable(self):
        a = LocalAgent(config_path="config.yaml")
        a.enabled = False
        self.assertFalse(a._available())

    def test_unavailable_raises(self):
        a = LocalAgent(config_path="config.yaml", model="nope")
        a.enabled = True
        a.base_url = "http://127.0.0.1:1"  # nothing listening
        with self.assertRaises(LocalAgentError):
            a.run("hello")

    def test_make_local_agent_none_when_disabled(self):
        self.assertIsNone(make_local_agent_proxy())


class RunStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = RunStateStore(self.tmp)

    def test_create_and_load(self):
        s = self.store.create("do the thing", mode="swarm")
        loaded = self.store.load(s.run_id)
        self.assertEqual(loaded.goal, "do the thing")
        self.assertEqual(loaded.mode, "swarm")
        self.assertEqual(loaded.next_phase, PHASE_ORDER[0])
        self.assertEqual(loaded.status, "running")

    def test_mark_phase_progresses(self):
        s = self.store.create("g")
        self.store.mark_phase(s.run_id, "decompose", artifact_path=None, note="ok")
        loaded = self.store.load(s.run_id)
        self.assertEqual([p["phase"] for p in loaded.completed_phases], ["decompose"])
        self.assertEqual(loaded.next_phase, "swarm")

    def test_mark_phase_is_idempotent(self):
        s = self.store.create("g")
        self.store.mark_phase(s.run_id, "decompose")
        self.store.mark_phase(s.run_id, "decompose")
        loaded = self.store.load(s.run_id)
        self.assertEqual(len(loaded.completed_phases), 1)

    def test_completion(self):
        s = self.store.create("g")
        for phase in PHASE_ORDER:
            self.store.mark_phase(s.run_id, phase)
        loaded = self.store.load(s.run_id)
        self.assertTrue(loaded.all_phases_done())
        self.assertIsNone(loaded.next_to_run())

    def test_list_runs(self):
        self.store.create("first goal")
        self.store.create("second goal")
        runs = list_runs(self.tmp)
        self.assertEqual(len(runs), 2)

    def test_load_missing_returns_none(self):
        self.assertIsNone(self.store.load("does-not-exist"))


class BatchRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmp, "config.yaml")
        Path(self.cfg_path).write_text(
            "openrouter:\n  api_key: test\n  base_url: https://example.invalid\n  model: openai/gpt-4.1-mini\n"
            "orchestrator:\n  parallel_agents: 4\n  task_timeout: 60\n  aggregation_strategy: consensus\n"
            "  question_generation_prompt: 'x'\n  synthesis_prompt: 'y'\n"
            "system_prompt: 's'\n"
            "apex_agents:\n"
            "  - role: source_researcher\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: claim_auditor\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: counter_analyst\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
            "  - role: review_planner\n    model: openai/gpt-4.1-mini\n    allowed_tools: []\n    system_prompt: 's'\n"
        )

    def test_batch_checkpoints_all_phases(self):
        # Swarm will fail (no network key) but the checkpoint pipeline must
        # still record every phase and produce a resumable run state.
        with patch("make_it_heavy.batch._run_swarm_goal", return_value="SWARM_RESULT"):
            result = batch_run(
                "checkpoint test",
                config_path=self.cfg_path,
                run_dir=self.tmp,
            )
        self.assertEqual(result["status"], "completed")
        state = result["state"]
        phases = [p["phase"] for p in state["completed_phases"]]
        self.assertEqual(phases, list(PHASE_ORDER))
        self.assertTrue((Path(self.tmp) / f"{state['run_id']}.synthesis.md").exists())

    def test_batch_resume_is_idempotent(self):
        with patch("make_it_heavy.batch._run_swarm_goal", return_value="X"):
            first = batch_run("resume test", config_path=self.cfg_path, run_dir=self.tmp)
        rid = first["run_id"]
        with patch("make_it_heavy.batch._run_swarm_goal", return_value="X") as spy:
            second = batch_run(
                "", config_path=self.cfg_path, run_dir=self.tmp, resume=rid
            )
        # Resuming must not re-run the swarm.
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(second["run_id"], rid)


if __name__ == "__main__":
    unittest.main()