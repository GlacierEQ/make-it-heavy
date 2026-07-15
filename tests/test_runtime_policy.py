import os
import tempfile
import time
import unittest
from unittest.mock import patch

from agent import (
    MAX_AGENT_TIMEOUT,
    MAX_REQUEST_TIMEOUT,
    OpenRouterAgent,
    _MockChoice,
    _MockMessage,
    _MockResponse,
    _bounded_agent_timeout,
    _bounded_timeout,
)
from orchestrator import (
    RESULT_CLASSIFICATION,
    REVIEW_STATUS,
    TaskOrchestrator,
)
from tools import discover_tools
from tools.write_file_tool import WriteFileTool


CONFIG_TEMPLATE = """
openrouter:
  api_key: test-key
  base_url: https://example.invalid/api/v1
  model: default-model
  request_timeout: 2
system_prompt: generic prompt
tools:
  allowlist: [search_web, calculate, read_file, mark_task_complete]
  mutation_enabled: false
apex_agents:
  - role: source_researcher
    model: role-model
    system_prompt: role-specific prompt
    allowed_tools: [calculate, mark_task_complete]
agent:
  max_iterations: 2
  run_timeout: 3
orchestrator:
  parallel_agents: 1
  task_timeout: {task_timeout}
  aggregation_strategy: consensus
  question_generation_prompt: "Return {num_agents} questions for {user_input}"
  synthesis_prompt: "Preserve uncertainty across {num_responses}: {agent_responses}"
"""


class ConfigCase(unittest.TestCase):
    def make_config(self, task_timeout=1):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        )
        # Escape braces intended for the runtime format operation.
        text = CONFIG_TEMPLATE.replace("{task_timeout}", str(task_timeout))
        handle.write(text)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return handle.name


class ToolPolicyTests(unittest.TestCase):
    def test_explicit_allowlist_excludes_unrequested_tools(self):
        tools = discover_tools(
            {"tools": {"allowlist": ["calculate"], "mutation_enabled": False}},
            silent=True,
        )
        self.assertEqual(set(tools), {"calculate"})

    def test_write_tool_needs_allowlist_and_mutation_opt_in(self):
        tools = discover_tools(
            {
                "tools": {
                    "allowlist": ["calculate", "write_file"],
                    "mutation_enabled": False,
                }
            },
            silent=True,
        )
        self.assertEqual(set(tools), {"calculate"})

    def test_unknown_tool_is_rejected(self):
        with self.assertRaises(ValueError):
            discover_tools(
                {"tools": {"allowlist": ["dropped_in_plugin"]}},
                silent=True,
            )

    def test_write_execution_is_denied_without_mutation_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "should-not-exist.txt")
            result = WriteFileTool({"tools": {"mutation_enabled": False}}).execute(
                target, "data"
            )
            self.assertFalse(result["success"])
            self.assertIn("denied", result["error"])
            self.assertFalse(os.path.exists(target))


class BindingAndClassificationTests(ConfigCase):
    def test_agent_binds_role_model_prompt_and_allowed_tools(self):
        agent = OpenRouterAgent(
            self.make_config(),
            role="bound-role",
            model="bound-model",
            system_prompt="bound prompt",
            allowed_tools=["calculate"],
        )
        self.assertEqual(agent.role, "bound-role")
        self.assertEqual(agent.model, "bound-model")
        self.assertEqual(agent.system_prompt, "bound prompt")
        self.assertEqual(set(agent.tool_mapping), {"calculate"})

    def test_worker_uses_its_profile_and_returns_honest_classification(self):
        seen = {}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                seen.update(kwargs)

            def run(self, subtask):
                seen["subtask"] = subtask
                return "A source-oriented model response"

        orchestrator = TaskOrchestrator(self.make_config())
        with patch("orchestrator.OpenRouterAgent", FakeAgent):
            result = orchestrator.run_agent_parallel(0, "audit this")

        self.assertEqual(seen["role"], "source_researcher")
        self.assertEqual(seen["model"], "role-model")
        self.assertEqual(seen["system_prompt"], "role-specific prompt")
        self.assertEqual(seen["allowed_tools"], ["calculate", "mark_task_complete"])
        self.assertEqual(result["status"], RESULT_CLASSIFICATION)
        self.assertEqual(result["review_status"], REVIEW_STATUS)
        self.assertIn("citation", result["source_expectation"])

    def test_request_timeout_is_bounded(self):
        self.assertEqual(_bounded_timeout(9999), MAX_REQUEST_TIMEOUT)
        self.assertEqual(_bounded_timeout(0), 1.0)
        self.assertEqual(_bounded_agent_timeout(9999), MAX_AGENT_TIMEOUT)

    def test_agent_passes_remaining_run_budget_to_request(self):
        agent = OpenRouterAgent(self.make_config(), allowed_tools=[])
        agent.agent_timeout = 0.2
        seen = {}

        def fake_call(_messages, request_timeout=None):
            seen["request_timeout"] = request_timeout
            return _MockResponse([_MockChoice(_MockMessage("done", None))])

        agent.call_llm = fake_call
        self.assertEqual(agent.run("test"), "done")
        self.assertGreater(seen["request_timeout"], 0)
        self.assertLessEqual(seen["request_timeout"], 0.2)

    def test_global_timeout_returns_without_waiting_for_worker(self):
        orchestrator = TaskOrchestrator(self.make_config(task_timeout=0.03))
        orchestrator.decompose_task = lambda _query, _count: ["slow"]

        def slow_worker(_agent_id, _subtask):
            time.sleep(0.25)
            return {"agent_id": 0, "status": RESULT_CLASSIFICATION, "response": "late"}

        orchestrator.run_agent_parallel = slow_worker
        orchestrator.aggregate_results = lambda _results: "bounded"
        started = time.monotonic()
        result = orchestrator.orchestrate("test")
        elapsed = time.monotonic() - started

        self.assertEqual(result, "bounded")
        self.assertLess(elapsed, 0.15)
        self.assertEqual(orchestrator.last_run_results[0]["status"], "timeout")

    def test_synthesis_prompt_preserves_uncertainty(self):
        seen = {}

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                seen["system_prompt"] = kwargs["system_prompt"]

            def run(self, prompt):
                seen["prompt"] = prompt
                return "uncertainty retained"

        orchestrator = TaskOrchestrator(self.make_config())
        worker_results = [
            {
                "agent_id": 0,
                "role": "source_researcher",
                "status": RESULT_CLASSIFICATION,
                "response": "An uncited assertion",
            },
            {
                "agent_id": 1,
                "role": "counter_analyst",
                "status": RESULT_CLASSIFICATION,
                "response": "A conflicting assertion",
            },
        ]
        with patch("orchestrator.OpenRouterAgent", FakeAgent):
            result = orchestrator._aggregate_consensus(worker_results)

        self.assertEqual(result, "uncertainty retained")
        self.assertIn("Preserve disagreements", seen["system_prompt"])
        self.assertIn("unreviewed model inference", seen["prompt"])


if __name__ == "__main__":
    unittest.main()
