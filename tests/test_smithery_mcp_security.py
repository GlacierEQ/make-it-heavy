import os
import unittest
from unittest.mock import Mock, patch

from tools import discover_tools
from tools.smithery_mcp_tool import SmitheryMCPTool


class SmitheryToolPolicyTests(unittest.TestCase):
    def config(self, mutation_enabled=True):
        return {
            "tools": {"mutation_enabled": mutation_enabled},
            "smithery": {
                "api_key": "test-key",
                "namespace_url": "https://mcp.example.invalid/namespace",
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

    def test_http_error_is_not_reported_as_success(self):
        response = Mock(status_code=401, text="credential detail must not be returned")
        with patch.dict(os.environ, {}, clear=True):
            tool = SmitheryMCPTool(self.config())
        with patch("tools.smithery_mcp_tool.requests.post", return_value=response):
            result = tool.execute("github", "read", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 401)
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
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["json"]["method"], "tools/call")
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Bearer "))


if __name__ == "__main__":
    unittest.main()
