# SPDX-License-Identifier: Proprietary
"""Agent memory read/write tool for persistent swarm memory."""

import json
import logging
from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class MemoryTool(BaseTool):
    """Read from or write to the persistent swarm memory."""

    def __init__(self, config: dict):
        from memory import SwarmMemory
        self.memory = SwarmMemory(config.get("memory", {}).get("db_path", ".swarm_memory.db"))

    @property
    def name(self):
        return "memory"

    @property
    def description(self):
        return (
            "Read from or write to the persistent swarm memory. "
            "Use this to recall past missions, store findings, or check system statistics."
        )

    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["recall_similar", "store", "get_stats"],
                    "description": "recall_similar: find past missions like the current one. store: save a key-value pair. get_stats: show system telemetry."
                },
                "query": {"type": "string", "description": "For recall_similar"},
                "key": {"type": "string", "description": "For store"},
                "value": {"type": "string", "description": "For store"}
            },
            "required": ["action"]
        }

    def execute(self, action: str, query: str = "", key: str = "", value: str = ""):
        if action == "recall_similar":
            return {"success": True, "past_missions": self.memory.get_similar_missions(query)}
        elif action == "store":
            self.memory.set_cache(key, value, ttl_seconds=86400 * 30)
            return {"success": True, "stored_key": key}
        elif action == "get_stats":
            return {"success": True, "stats": self.memory.get_stats()}
        return {"success": False, "error": "Unknown action"}
