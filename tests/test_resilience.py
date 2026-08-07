# SPDX-License-Identifier: Proprietary
"""Unit tests for retry, circuit breaker, and caching in OpenRouterAgent."""

import unittest
from unittest.mock import patch, MagicMock
from agent import OpenRouterAgent, LLMCallError


class TestResilience(unittest.TestCase):
    @patch("agent.discover_tools")
    @patch("agent.SwarmMemory")
    @patch("agent.OpenAI")
    @patch("agent.yaml.safe_load")
    def test_circuit_breaker_opens_after_threshold(self, mock_yaml, mock_openai, mock_mem, mock_disc):
        mock_yaml.return_value = {
            "openrouter": {"api_key": "test", "base_url": "http://test", "model": "test"},
            "system_prompt": "test",
            "agent": {"max_iterations": 3, "run_timeout": 10},
            "tools": {"allowlist": [], "mutation_enabled": False},
            "apex_agents": [],
            "orchestrator": {"parallel_agents": 1, "task_timeout": 10, "aggregation_strategy": "consensus", "question_generation_prompt": "", "synthesis_prompt": ""}
        }
        mock_disc.return_value = {}
        mock_mem.return_value.get_cache.return_value = None
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = LLMCallError("HTTP 500")

        agent = OpenRouterAgent(silent=True)
        with patch("agent.time.sleep") as mock_sleep, patch(
            "agent.random.random", return_value=0.0
        ):
            for _ in range(5):
                try:
                    agent.call_llm([{"role": "user", "content": "test"}])
                except LLMCallError:
                    pass

        self.assertTrue(agent._circuit_open())
        self.assertEqual(mock_sleep.call_count, 15)
        self.assertEqual(mock_client.chat.completions.create.call_count, 15)

    @patch("agent.discover_tools")
    @patch("agent.SwarmMemory")
    @patch("agent.OpenAI")
    @patch("agent.yaml.safe_load")
    def test_cache_hit_avoids_llm_call(self, mock_yaml, mock_openai, mock_mem, mock_disc):
        mock_yaml.return_value = {
            "openrouter": {"api_key": "test", "base_url": "http://test", "model": "test"},
            "system_prompt": "test",
            "agent": {"max_iterations": 3, "run_timeout": 10},
            "tools": {"allowlist": [], "mutation_enabled": False},
            "apex_agents": [],
            "orchestrator": {"parallel_agents": 1, "task_timeout": 10, "aggregation_strategy": "consensus", "question_generation_prompt": "", "synthesis_prompt": ""}
        }
        mock_disc.return_value = {}
        mock_mem.return_value.get_cache.return_value = "cached response"
        mock_client = mock_openai.return_value

        agent = OpenRouterAgent(silent=True)
        resp = agent.call_llm([{"role": "user", "content": "test"}])

        self.assertEqual(resp.choices[0].message.content, "cached response")
        mock_client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
