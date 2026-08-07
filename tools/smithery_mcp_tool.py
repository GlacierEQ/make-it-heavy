# SPDX-License-Identifier: Proprietary
"""Smithery MCP connector — lets agents call explicitly enabled MCP servers."""

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
        smithery = config.get("smithery", {})
        self.smithery_key = os.environ.get("SMITHERY_KEY") or smithery.get(
            "api_key", ""
        )
        self.namespace_url = smithery.get("namespace_url", "")
        allowed_connections = smithery.get("allowed_connections", [])
        if not isinstance(allowed_connections, (list, tuple, set)):
            allowed_connections = []
        self.allowed_connections = frozenset(
            value
            for value in allowed_connections
            if isinstance(value, str) and value.strip()
        )
        self.mutation_enabled = config.get("tools", {}).get("mutation_enabled") is True
        try:
            configured_timeout = float(smithery.get("request_timeout", 60))
        except (TypeError, ValueError):
            configured_timeout = 60.0
        self.request_timeout = min(max(configured_timeout, 0.1), 60.0)

    @property
    def name(self):
        return "smithery_mcp"

    @property
    def description(self):
        return (
            "Call an explicitly allowlisted Smithery MCP connection. "
            "This is a privileged boundary because connected servers may expose writes. "
            "Requires the connection_id, tool_name, and arguments."
        )

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "Allowlisted Smithery connection id"},
                "tool_name": {"type": "string", "description": "Exact remote MCP tool name"},
                "arguments": {"type": "object", "description": "Tool arguments as a JSON object"},
            },
            "required": ["connection_id", "tool_name", "arguments"],
        }

    def execute(
        self,
        connection_id: str,
        tool_name: str,
        arguments: dict,
        _timeout_seconds: float = None,
    ):
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
        if connection_id not in self.allowed_connections:
            return {
                "success": False,
                "error": "Smithery MCP connection is not allowlisted.",
            }

        request_timeout = self.request_timeout
        if _timeout_seconds is not None:
            try:
                remaining_budget = float(_timeout_seconds)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "Smithery MCP received an invalid request budget.",
                }
            if remaining_budget <= 0:
                return {
                    "success": False,
                    "error": "Smithery MCP request budget is exhausted.",
                }
            request_timeout = min(request_timeout, max(remaining_budget, 0.01))

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
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=request_timeout,
            )
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
        except ValueError:
            return {
                "success": False,
                "status": resp.status_code,
                "error": "Smithery MCP response was not valid JSON.",
            }

        if not isinstance(rpc_response, dict) or rpc_response.get("jsonrpc") != "2.0":
            return {
                "success": False,
                "status": resp.status_code,
                "error": "Smithery MCP response was not a valid JSON-RPC 2.0 object.",
            }

        if rpc_response.get("error") is not None:
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

        if "result" not in rpc_response:
            return {
                "success": False,
                "status": resp.status_code,
                "error": "Smithery MCP response was missing a JSON-RPC result.",
            }

        return {
            "success": True,
            "status": resp.status_code,
            "data": resp.text[:4000],
        }
