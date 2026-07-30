# SPDX-License-Identifier: Proprietary
"""Unit tests for SwarmScheduler."""

import unittest
from unittest.mock import patch, MagicMock
from scheduler import SwarmScheduler


class TestSwarmScheduler(unittest.TestCase):
    @patch("scheduler.TaskOrchestrator")
    @patch("scheduler.SwarmMemory")
    def test_add_mission(self, mock_memory, mock_orch):
        sched = SwarmScheduler("config.yaml")
        sched.add_mission("test mission", "every().hour")
        self.assertTrue(sched.running is False)

    @patch("scheduler.TaskOrchestrator")
    @patch("scheduler.SwarmMemory")
    def test_run_mission_success(self, mock_memory_cls, mock_orch_cls):
        mock_orch = mock_orch_cls.return_value
        mock_orch.run_mission.return_value = "success"
        mock_mem = mock_memory_cls.return_value
        mock_mem.start_mission.return_value = 42

        sched = SwarmScheduler("config.yaml")
        sched._run_mission("test")

        mock_mem.start_mission.assert_called_once_with("test")
        mock_orch.run_mission.assert_called_once_with("test")
        mock_mem.complete_mission.assert_called_once_with(42, "success", "completed")

    @patch("scheduler.TaskOrchestrator")
    @patch("scheduler.SwarmMemory")
    def test_run_mission_failure(self, mock_memory_cls, mock_orch_cls):
        mock_orch = mock_orch_cls.return_value
        mock_orch.run_mission.side_effect = RuntimeError("boom")
        mock_mem = mock_memory_cls.return_value
        mock_mem.start_mission.return_value = 99

        sched = SwarmScheduler("config.yaml")
        sched._run_mission("test")

        mock_mem.complete_mission.assert_called_once_with(99, "boom", "failed")


if __name__ == "__main__":
    unittest.main()
