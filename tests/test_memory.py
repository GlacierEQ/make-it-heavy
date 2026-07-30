# SPDX-License-Identifier: Proprietary
"""Unit tests for SwarmMemory persistence layer."""

import unittest
import tempfile
import os
from memory import SwarmMemory


class TestSwarmMemory(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.memory = SwarmMemory(self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_start_and_complete_mission(self):
        mid = self.memory.start_mission("test query")
        self.assertIsInstance(mid, int)
        self.memory.complete_mission(mid, "test result")
        stats = self.memory.get_stats()
        self.assertEqual(stats["total_missions"], 1)
        self.assertEqual(stats["total_agent_runs"], 0)

    def test_log_agent_run(self):
        mid = self.memory.start_mission("run test")
        self.memory.log_agent_run(mid, "source_researcher", "gpt-4", "response", 1.5)
        stats = self.memory.get_stats()
        self.assertEqual(stats["total_agent_runs"], 1)
        self.assertAlmostEqual(stats["avg_agent_execution_time"], 1.5, places=2)

    def test_log_tool_call(self):
        mid = self.memory.start_mission("tool test")
        self.memory.log_tool_call(mid, "auditor", "calculate", {"expr": "1+1"}, {"result": 2}, 12.3)
        stats = self.memory.get_stats()
        self.assertEqual(stats["total_tool_calls"], 1)

    def test_cache_roundtrip(self):
        self.memory.set_cache("key1", "value1", ttl_seconds=3600)
        self.assertEqual(self.memory.get_cache("key1"), "value1")

    def test_cache_expiration(self):
        self.memory.set_cache("key2", "value2", ttl_seconds=0)
        self.assertIsNone(self.memory.get_cache("key2"))

    def test_similar_missions(self):
        mid1 = self.memory.start_mission("query A")
        self.memory.complete_mission(mid1, "result A")
        mid2 = self.memory.start_mission("query B")
        self.memory.complete_mission(mid2, "result B")
        similar = self.memory.get_similar_missions("query A", limit=1)
        self.assertEqual(len(similar), 1)

    def test_hash_query_deterministic(self):
        h1 = self.memory.hash_query("same")
        h2 = self.memory.hash_query("same")
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
