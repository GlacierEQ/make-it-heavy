# SPDX-License-Identifier: Proprietary
"""Innovation-stage orchestrator with per-turn worker scoring and adaptation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from innovation_loop import AdaptiveWorkerLoop
from innovation_memory import AdaptiveSwarmMemory
from orchestrator import TaskOrchestrator


class AdaptiveTaskOrchestrator(TaskOrchestrator):
    """Run Make-It-Heavy through versioned templates and a measured next-turn loop."""

    def __init__(
        self,
        config_path: str = "innovation_config.yaml",
        silent: bool = False,
    ) -> None:
        super().__init__(config_path=config_path, silent=silent)
        innovation = self.config.get("innovation", {})
        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")
        self.memory = AdaptiveSwarmMemory(memory_path)
        template_path = Path(config_path).resolve().parent / innovation.get(
            "template_path",
            "templates/innovation_workers.yaml",
        )
        self.innovation = AdaptiveWorkerLoop(
            template_path,
            self.memory,
            min_workers=int(innovation.get("min_workers", 4)),
            max_workers=int(innovation.get("max_workers", 8)),
            target_quality=float(innovation.get("target_quality", 78.0)),
            target_benefit=float(innovation.get("target_benefit", 0.60)),
        )
        self.all_worker_profiles: Dict[str, Dict[str, Any]] = {
            str(profile["role"]): dict(profile)
            for profile in self.config["apex_agents"]
        }
        self.last_innovation_report: Dict[str, Any] = {}

    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:
        """Use exact worker templates instead of a generic decomposition model."""

        profiles = self.worker_profiles[:num_agents]
        return self.innovation.build_subtasks(user_input, profiles)

    def _activate_next_roles(self, roles: List[str]) -> None:
        selected = []
        for role in roles:
            profile = self.all_worker_profiles.get(role)
            if profile is None:
                continue
            selected.append(profile)
        if not selected:
            return
        self.worker_profiles = selected
        self.num_agents = len(selected)

    def orchestrate(self, user_input: str) -> str:
        """Execute, score, report, persist, and tune the next turn."""

        self._current_mission_id = self.memory.start_mission(user_input)
        try:
            synthesis = super().orchestrate(user_input)
            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                self.last_run_results,
                synthesis,
            )
            self.last_innovation_report = report
            final = f"{synthesis}\n\n{report['markdown']}"
            self.memory.complete_mission(
                self._current_mission_id,
                final,
                status="completed",
            )
            self._activate_next_roles(report["next_roles"])
            return final
        except Exception:
            self.memory.complete_mission(
                self._current_mission_id,
                "Innovation turn failed before completion.",
                status="failed",
            )
            raise
