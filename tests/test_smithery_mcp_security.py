import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import OpenRouterAgent, _MockChoice, _MockMessage, _MockResponse
from tools import discover_tools
from tools.smithery_mcp_tool import SmitheryMCPTool


class SmitheryToolPolicyTests(unittest.TestCase):
    def config(self, mutation_enabled=True):
        return {
            "tools": {"mutation_enabled": mutation_enabled},
            "smithery": {
                "api_key": "test-key",
                "namespace_url": "https://mcp.example.invalid/namespace",
                "allowed_connections": ["github"],
                "request_timeout": 60,
            },
        }

    def test_smithery_is_not_loaded_by_default(self):
        tools = discover_tools({}, silent=True)
        self.assertNotIn("smithery_mcp", tools)

    def test_smithery_requires_mutation_opt_in_even_when_allowlisted(self):
        tools = discover_tools(
            {
                **self.config(mutation_enabled=False),
                "tools": {
                    "allowlist": ["smithery_mcp"],
                    "mutation_enabled": False,
                },
            },
            silent=True,
        )
        self.assertEqual(tools, {})

    def test_direct_execution_denies_without_mutation_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config(mutation_enabled=False))
        result = tool.execute("github", "read", {})
        self.assertFalse(result["success"])
        self.assertIn("denied", result["error"].lower())

    def test_unconfigured_connection_is_denied_before_transport(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post") as post:
            result = tool.execute("not-allowlisted", "read", {})

        self.assertFalse(result["success"])
        self.assertIn("allowlisted", result["error"].lower())
        post.assert_not_called()

    def test_http_error_is_not_reported_as_success(self):
        response = Mock(status_code=401, text="credential detail must not be returned")
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response):
            result = tool.execute("github", "read", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 401)
        self.assertNotIn(response.text, result.values())

    def test_non_json_2xx_response_fails_closed_without_returning_body(self):
        response = Mock(status_code=200, text="upstream proxy error detail")
        response.json.side_effect = ValueError("not json")
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response):
            result = tool.execute("github", "read", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 200)
        self.assertNotIn(response.text, result.values())

    def test_json_rpc_error_is_not_reported_as_success(self):
        response = Mock(status_code=200, text='{"jsonrpc":"2.0","error":{"code":-32603}}')
        response.json.return_value = {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": "internal detail"},
        }
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response):
            result = tool.execute("github", "read", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["rpc_error_code"], -32603)
        self.assertNotIn("internal detail", result.values())

    def test_json_object_without_result_fails_closed(self):
        response = Mock(status_code=200, text='{"jsonrpc":"2.0","id":1}')
        response.json.return_value = {"jsonrpc": "2.0", "id": 1}
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response):
            result = tool.execute("github", "read", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 200)

    def test_remaining_budget_bounds_transport_timeout(self):
        body = '{"jsonrpc":"2.0","result":{"ok":true}}'
        response = Mock(status_code=200, text=body)
        response.json.return_value = {"jsonrpc": "2.0", "result": {"ok": True}}
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response) as post:
            result = tool.execute("github", "read", {}, _timeout_seconds=0.25)

        self.assertTrue(result["success"])
        self.assertEqual(post.call_args.kwargs["timeout"], 0.25)

    def test_agent_handler_injects_remaining_budget_into_smithery_call(self):
        agent = object.__new__(OpenRouterAgent)
        agent.role = "security-test"
        seen = {}
        agent.tool_mapping = {
            "smithery_mcp": lambda **kwargs: seen.update(kwargs) or {"success": True}
        }
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="smithery_mcp",
                arguments='{"connection_id":"github","tool_name":"read","arguments":{}}',
            ),
        )

        agent.handle_tool_call(tool_call, remaining_budget=0.4)

        self.assertEqual(seen["_timeout_seconds"], 0.4)

    def test_agent_run_passes_remaining_budget_to_tool_handler(self):
        agent = object.__new__(OpenRouterAgent)
        agent.role = "security-test"
        agent.system_prompt = "test"
        agent.max_iterations = 2
        agent.agent_timeout = 1.0
        agent.request_timeout = 1.0
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="smithery_mcp", arguments="{}"),
        )
        responses = iter(
            [
                _MockResponse([_MockChoice(_MockMessage(None, [tool_call]))]),
                _MockResponse([_MockChoice(_MockMessage("done", None))]),
            ]
        )
        agent.call_llm = lambda messages, request_timeout=None: next(responses)
        seen = {}

        def fake_handle(call, remaining_budget=None):
            seen["remaining_budget"] = remaining_budget
            return {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.function.name,
                "content": '{"success":true}',
            }

        agent.handle_tool_call = fake_handle
        result = agent.run("test")

        self.assertEqual(result, "done")
        self.assertGreater(seen["remaining_budget"], 0)
        self.assertLessEqual(seen["remaining_budget"], agent.agent_timeout)

    def test_successful_rpc_preserves_existing_text_data_contract(self):
        body = '{"jsonrpc":"2.0","result":{"ok":true}}'
        response = Mock(status_code=200, text=body)
        response.json.return_value = {"jsonrpc": "2.0", "result": {"ok": True}}
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response) as post:
            result = tool.execute("github", "read", {"repo": "example"})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"], body)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 60.0)
        self.assertEqual(kwargs["json"]["method"], "tools/call")
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Bearer "))


if __name__ == "__main__":
    unittest.main()
