# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""Autonomous scheduler for Make-It-Heavy missions.

Runs missions on a schedule with full memory persistence and error recovery.
Works offline — no external schedule package required.
"""

import time
import threading
import logging
from typing import Callable, Optional
from orchestrator import TaskOrchestrator
from memory import SwarmMemory

logger = logging.getLogger(__name__)


class SwarmScheduler:
    """Autonomous scheduler for Make-It-Heavy missions.

    Uses a background thread with simple sleep polling.
    No external dependencies beyond the Python standard library.
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.orchestrator = TaskOrchestrator(config_path, silent=True)
        self.memory = SwarmMemory()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._jobs: list = []
        self._lock = threading.Lock()

    def add_mission(self, query: str, interval_seconds: int = 3600):
        """Schedule a mission to run every interval_seconds."""
        with self._lock:
            self._jobs.append({"query": query, "interval": interval_seconds, "last_run": 0})
        logger.info("Scheduled mission: '%s' every %ds", query, interval_seconds)

    def add_mission_cron(self, query: str, hour: int = 0, minute: int = 0):
        """Schedule a mission to run daily at a specific time."""
        with self._lock:
            self._jobs.append({"query": query, "hour": hour, "minute": minute, "last_run_day": -1})
        logger.info("Scheduled mission: '%s' daily at %02d:%02d", query, hour, minute)

    def _run_mission(self, query: str):
        logger.info("Running scheduled mission: %s", query)
        mission_id = self.memory.start_mission(query)
        try:
            result = self.orchestrator.run_mission(query)
            self.memory.complete_mission(mission_id, result, "completed")
            logger.info("Mission completed: %s", query)
        except Exception as exc:
            self.memory.complete_mission(mission_id, str(exc), "failed")
            logger.error("Mission failed: %s — %s", query, exc)

    def _tick(self):
        """Check all jobs and run any that are due."""
        now = time.time()
        with self._lock:
            for job in self._jobs:
                if "interval" in job:
                    if now - job["last_run"] >= job["interval"]:
                        job["last_run"] = now
                        threading.Thread(target=self._run_mission, args=(job["query"],), daemon=True).start()
                elif "hour" in job:
                    import datetime
                    dt = datetime.datetime.now()
                    today = dt.toordinal()
                    if dt.hour >= job["hour"] and dt.minute >= job["minute"] and job.get("last_run_day") != today:
                        job["last_run_day"] = today
                        threading.Thread(target=self._run_mission, args=(job["query"],), daemon=True).start()

    def run(self, tick_interval: int = 60):
        """Start the scheduler loop. Blocks until stop() is called."""
        self.running = True
        logger.info("SwarmScheduler started (tick every %ds). Press Ctrl+C to stop.", tick_interval)
        try:
            while self.running:
                self._tick()
                time.sleep(tick_interval)
        except KeyboardInterrupt:
            logger.info("SwarmScheduler interrupted.")
        finally:
            self.running = False

    def run_once(self, query: str):
        """Run a single mission immediately (blocking)."""
        self._run_mission(query)

    def stop(self):
        self.running = False
