# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""Autonomous hourly scheduler for Make-It-Heavy missions.

Runs missions on a schedule with full memory persistence and error recovery.
"""

import schedule
import time
import logging
from orchestrator import TaskOrchestrator
from memory import SwarmMemory

logger = logging.getLogger(__name__)


class SwarmScheduler:
    """Autonomous hourly scheduler for Make-It-Heavy missions."""

    def __init__(self, config_path: str = "config.yaml"):
        self.orchestrator = TaskOrchestrator(config_path, silent=True)
        self.memory = SwarmMemory()
        self.running = False

    def add_mission(self, query: str, schedule_str: str = "every().hour"):
        """schedule_str: 'every().hour', 'every().day.at("10:30")', etc."""
        job = getattr(schedule, schedule_str.split('.')[1])
        if 'at(' in schedule_str:
            time_part = schedule_str.split('at(')[1].split(')')[0].strip('"')
            job = job.at(time_part)
        job.do(self._run_mission, query)
        logger.info(f"Scheduled mission: '{query}' with '{schedule_str}'")

    def _run_mission(self, query: str):
        logger.info(f"Running scheduled mission: {query}")
        mission_id = self.memory.start_mission(query)
        try:
            result = self.orchestrator.run_mission(query)
            self.memory.complete_mission(mission_id, result, "completed")
            logger.info(f"Mission completed: {query}")
        except Exception as exc:
            self.memory.complete_mission(mission_id, str(exc), "failed")
            logger.error(f"Mission failed: {query} — {exc}")

    def run(self):
        self.running = True
        logger.info("SwarmScheduler started. Press Ctrl+C to stop.")
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def stop(self):
        self.running = False
