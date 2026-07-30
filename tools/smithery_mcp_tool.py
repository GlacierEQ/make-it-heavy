# SPDX-License-Identifier: Proprietary
"""Smithery MCP connector — lets agents call any connected MCP server."""

import requests
import json
import os
import logging
from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class SmitheryMCPTool(BaseTool):
    """Call another Smithery MCP server from the swarm tool loop.

    This unlocks GitHub, Notion, Google Drive, Sheets, and all 44+ connections
    from inside agent reasoning.
    """

    def __init__(self, config: dict):
        self.config = config
        self.smithery_key = os.environ.get("SMITHERY_KEY") or config.get("smithery", {}).get("api_key", "")
        self.namespace_url = config.get("smithery", {}).get("namespace_url", "")

    @property
    def name(self):
        return "smithery_mcp"

    @property
    def description(self):
        return (
            "Call another Smithery MCP server from the swarm. "
            "Use this to interact with GitHub, Notion, Google Drive, or any connected system. "
            "Requires the connection_id (e.g., 'github', 'notion', 'googledrive')."
        )

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "e.g., 'github', 'notion', 'googledrive'"},
                "tool_name": {"type": "string", "description": "Full tool name, e.g., 'github.search_repositories'"},
                "arguments": {"type": "object", "description": "Tool arguments as JSON object"}
            },
            "required": ["connection_id", "tool_name", "arguments"]
        }

    def execute(self, connection_id: str, tool_name: str, arguments: dict):
        if not self.smithery_key or not self.namespace_url:
            return {"success": False, "error": "Smithery not configured. Set SMITHERY_KEY and namespace_url."}

        url = f"{self.namespace_url}/{connection_id}"
        headers = {
            "Authorization": f"Bearer {self.smithery_key}",
            "Content-Type": "application/json",
            "Mcp-Session-Id": f"swarm-{connection_id}"
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            return {"success": True, "status": resp.status_code, "data": resp.text[:4000]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
