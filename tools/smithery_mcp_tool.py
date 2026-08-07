# SPDX-License-Identifier: Proprietary
"""Smithery MCP connector — lets agents call explicitly enabled MCP servers."""

import json
import logging
import os

import requests

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class SmitheryMCPTool(BaseTool):
    """Call another Smithery MCP server through a privileged tool boundary.

    Smithery can expose both read and write capabilities. The connector therefore
    requires the repository-wide mutation opt-in even when a particular remote
    call is expected to be read-only.
    """

    def __init__(self, config: dict):
        self.config = config
        self.smithery_key = os.environ.get("SMITHERY_KEY") or config.get(
            "smithery", {}
        ).get("api_key", "")
        self.namespace_url = config.get("smithery", {}).get("namespace_url", "")
        self.mutation_enabled = config.get("tools", {}).get("mutation_enabled") is True

    @property
    def name(self):
        return "smithery_mcp"

    @property
    def description(self):
        return (
            "Call an explicitly enabled Smithery MCP connection. "
            "This is a privileged boundary because connected servers may expose writes. "
            "Requires the connection_id, tool_name, and arguments."
        )

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "Configured Smithery connection id"},
                "tool_name": {"type": "string", "description": "Exact remote MCP tool name"},
                "arguments": {"type": "object", "description": "Tool arguments as a JSON object"},
            },
            "required": ["connection_id", "tool_name", "arguments"],
        }

    def execute(self, connection_id: str, tool_name: str, arguments: dict):
        if not self.mutation_enabled:
            return {
                "success": False,
                "error": "Smithery MCP denied: tools.mutation_enabled is not true.",
            }
        if not self.smithery_key or not self.namespace_url:
            return {
                "success": False,
                "error": "Smithery not configured. Set SMITHERY_KEY and namespace_url.",
            }

        url = f"{self.namespace_url.rstrip('/')}/{connection_id}"
        headers = {
            "Authorization": f"Bearer {self.smithery_key}",
            "Content-Type": "application/json",
            "Mcp-Session-Id": f"swarm-{connection_id}",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            logger.warning("Smithery MCP transport failure: %s", type(exc).__name__)
            return {"success": False, "error": "Smithery MCP transport failure."}
        except Exception as exc:
            logger.warning("Smithery MCP unexpected transport failure: %s", type(exc).__name__)
            return {"success": False, "error": "Smithery MCP transport failure."}

        if not 200 <= resp.status_code < 300:
            return {
                "success": False,
                "status": resp.status_code,
                "error": "Smithery MCP request failed.",
            }

        try:
            rpc_response = resp.json()
        except (ValueError, json.JSONDecodeError):
            rpc_response = None

        if isinstance(rpc_response, dict) and rpc_response.get("error") is not None:
            rpc_error = rpc_response["error"]
            error_code = rpc_error.get("code") if isinstance(rpc_error, dict) else None
            result = {
                "success": False,
                "status": resp.status_code,
                "error": "Smithery MCP returned a JSON-RPC error.",
            }
            if error_code is not None:
                result["rpc_error_code"] = error_code
            return result

        return {
            "success": True,
            "status": resp.status_code,
            "data": resp.text[:4000],
        }
