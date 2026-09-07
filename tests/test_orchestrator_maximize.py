# SPDX-License-Identifier: Proprietary
"""Tests for the "maximize the orchestrator" capabilities.

Covers: bounded wave concurrency, per-role max_iterations enforcement,
synthesis token budget + aggregation_strategy branching, memoized decompose,
and the user_id / TieredMemory no-op + empty-user_id guard.
"""

import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import yaml

from orchestrator import (
    TaskOrchestrator,
    bounded_provider_concurrency,
    effective_turn_timeout,
)
from memory_tiered import TieredMemory


ROLES = (
    "source_researcher",
    "claim_auditor",
    "counter_analyst",
    "review_planner",
)


def build_config(extra_orchestrator="", agent_block="  max_iterations: 10\n  run_timeout: 5\n"):
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", encoding="utf-8", delete=False
    )
    agents = "\n".join(
        f"  - role: {role}\n"
        f"    model: openai/gpt-4.1-mini\n"
        f"    allowed_tools: []\n"
        f"    system_prompt: 's'\n"
        for role in ROLES
    )
    text = """
openrouter:
  api_key: test-key
  base_url: https://example.invalid/api/v1
  model: openai/gpt-4.1-mini
  request_timeout: 2
system_prompt: generic
tools:
  allowlist: [search_web]
  mutation_enabled: false
apex_agents:
{agents}
agent:
{agent_block}
orchestrator:
  parallel_agents: 4
  provider_concurrency_width: 2
  task_timeout: 30
  aggregation_strategy: consensus
  question_generation_prompt: "Return {num_agents} questions for {user_input}"
  synthesis_prompt: "Preserve uncertainty across {num_responses}: {agent_responses}"
{extra_orchestrator}
"""
    text = text.replace("{agents}", agents).replace("{agent_block}", agent_block).replace(
        "{extra_orchestrator}", extra_orchestrator
    )
    handle.write(text)
    handle.close()
    return handle.name


def save_config(raw):
    p = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.safe_dump(raw, p)
    p.close()
    return p.name


class WaveConcurrencyTests(unittest.TestCase):
    def test_bounded_helpers(self):
        self.assertEqual(bounded_provider_concurrency(7, 1), 1)
        self.assertEqual(bounded_provider_concurrency(7, 20), 7)
        self.assertEqual(effective_turn_timeout(10, 4, 2), 20)
        self.assertEqual(effective_turn_timeout(10, 1, 1), 10)

    def test_provider_width_bounded_to_num_agents(self):
        orch = TaskOrchestrator(build_config())
        self.assertEqual(orch.provider_concurrency_width, 2)
        self.assertEqual(
            bounded_provider_concurrency(orch.num_agents, orch.provider_concurrency_width),
            2,
        )

    def test_waves_never_exceed_provider_width(self):
        orch = TaskOrchestrator(build_config())
        lock = threading.Lock()
        state = {"active": 0, "peak": 0}
        calls = []

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                self._role = kwargs.get("role")

            def run(self, subtask):
                # Only worker roles drive the concurrency we want to bound;
                # decompose/synthesis agents run unmeasured.
                if self._role in ROLES:
                    with lock:
                        state["active"] += 1
                        state["peak"] = max(state["peak"], state["active"])
                    time.sleep(0.03)
                    with lock:
                        state["active"] -= 1
                    calls.append(subtask)
                return "worker result"

        with patch("orchestrator.OpenRouterAgent", FakeAgent):
            result = orch.orchestrate("goal")
        self.assertEqual(len(calls), 4)
        self.assertLessEqual(state["peak"], 2)
        self.assertIn("RESULT CLASSIFICATION", result)


class MaxIterationsEnforcementTests(unittest.TestCase):
    def test_per_role_max_iterations_passed_to_agent(self):
        # source_researcher declares 3; claim_auditor inherits the default 5.
        with open(build_config(agent_block="  max_iterations: 5\n  run_timeout: 5\n")) as fh:
            raw = yaml.safe_load(fh)
        raw["apex_agents"][0]["max_iterations"] = 3
        orch = TaskOrchestrator(save_config(raw))

        captured = {}

        class CaptureAgent:
            def __init__(self, *args, **kwargs):
                captured[kwargs.get("role")] = kwargs

            def run(self, subtask):
                return "ok"

        with patch("orchestrator.OpenRouterAgent", CaptureAgent):
            orch.run_agent_parallel(0, "x")
            orch.run_agent_parallel(1, "x")
        self.assertEqual(captured["source_researcher"]["max_iterations"], 3)
        self.assertEqual(captured["claim_auditor"]["max_iterations"], 5)


class SynthesisBudgetTests(unittest.TestCase):
    def test_compact_strategy_bounded_without_llm(self):
        orch = TaskOrchestrator(
            build_config(
                extra_orchestrator=(
                    "  aggregation_strategy: compact\n"
                    "  synthesis_token_budget: 5\n"
                )
            )
        )
        results = [
            {
                "agent_id": i,
                "role": role,
                "status": "model_inference",
                "response": "x" * 200,
            }
            for i, role in enumerate(ROLES)
        ]
        calls = []

        class NoLLM:
            def __init__(self, *args, **kwargs):
                calls.append(kwargs.get("role"))

            def run(self, subtask):
                return "should not be called"

        with patch("orchestrator.OpenRouterAgent", NoLLM):
            body = orch.aggregate_results(results)
        self.assertEqual(calls, [])  # compact path makes no LLM call
        self.assertIn("truncated to synthesis budget", body)
        for role in ROLES:
            self.assertIn(role, body)
        # Bounded well below the uncompacted ~4*200 chars.
        self.assertLess(len(body), 600)

    def test_vote_strategy_bounded_without_llm(self):
        orch = TaskOrchestrator(
            build_config(
                extra_orchestrator=(
                    "  aggregation_strategy: vote\n"
                    "  synthesis_token_budget: 5\n"
                )
            )
        )
        results = [
            {"agent_id": i, "role": role, "status": "model_inference", "response": "y" * 200}
            for i, role in enumerate(ROLES)
        ]
        with patch("orchestrator.OpenRouterAgent", side_effect=AssertionError("no LLM")):
            body = orch.aggregate_results(results)
        self.assertIn("VOTE", body)

    def test_consensus_strategy_still_uses_llm(self):
        orch = TaskOrchestrator(build_config())
        results = [
            {"agent_id": 0, "role": "source_researcher", "status": "model_inference",
             "response": "one"},
            {"agent_id": 1, "role": "claim_auditor", "status": "model_inference",
             "response": "two"},
        ]
        seen = {}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                seen["role"] = kwargs.get("role")

            def run(self, prompt):
                seen["prompt"] = prompt
                return "synthesized"

        with patch("orchestrator.OpenRouterAgent", FakeAgent):
            body = orch.aggregate_results(results)
        self.assertEqual(seen["role"], "synthesis_reviewer")
        self.assertIn("synthesized", body)


class DecomposeMemoizationTests(unittest.TestCase):
    def test_subtasks_skip_decompose(self):
        orch = TaskOrchestrator(build_config())
        calls = []
        orch.decompose_task = lambda u, n: (calls.append((u, n)) or [f"s{i}" for i in range(n)])
        orch.orchestrate("goal", subtasks=["a", "b", "c", "d"])
        self.assertEqual(calls, [])  # R1: no LLM decompose when subtasks supplied

    def test_decompose_memoized_across_calls(self):
        orch = TaskOrchestrator(build_config())
        constructions = []

        class CountingAgent:
            def __init__(self, *args, **kwargs):
                constructions.append(kwargs.get("role"))

            def run(self, subtask):
                return ""  # forces deterministic fallback; cache still applies

        with patch("orchestrator.OpenRouterAgent", CountingAgent):
            orch.decompose_task("same input", orch.num_agents)
            orch.decompose_task("same input", orch.num_agents)
        # task_decomposer constructed only once; second call hit the cache.
        self.assertEqual(constructions.count("task_decomposer"), 1)


class UserIdMemoryTests(unittest.TestCase):
    def test_no_user_id_is_noop(self):
        orch = TaskOrchestrator(build_config())  # no user_id
        self.assertEqual(orch.user_id, "")
        self.assertEqual(orch._build_memory_context("anything"), "")

    def test_empty_user_id_never_reaches_tiered_memory(self):
        mem = TieredMemory(":memory:")
        with self.assertRaises(ValueError):
            mem.build_context("", "anything")

    def test_user_id_builds_memory_block(self):
        fd, db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # Point the orchestrator's tiered memory at the same DB we seed.
        cfg = build_config(
            extra_orchestrator=f"memory:\n  tiered_db_path: {db}\n"
        )
        seed = TieredMemory(db)
        seed.add_turn("alice", "user", "Casey lives in Seattle")
        try:
            orch = TaskOrchestrator(cfg, user_id="alice")
            self.assertEqual(orch.user_id, "alice")
            block = orch._build_memory_context("Where is Casey?")
            self.assertIn("<memory>", block)
            self.assertIn("Seattle", block)
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
