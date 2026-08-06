# SPDX-License-Identifier: Proprietary
"""Innovation-stage orchestrator with per-turn worker scoring and adaptation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from innovation_loop import AdaptiveWorkerLoop, InnovationConfigurationError
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
        profile_roles = set(self.all_worker_profiles)
        template_roles = set(self.innovation.templates_by_role)
        if profile_roles != template_roles:
            missing_profiles = sorted(template_roles - profile_roles)
            missing_templates = sorted(profile_roles - template_roles)
            raise InnovationConfigurationError(
                "profile/template role mismatch: "
                f"missing_profiles={missing_profiles}, "
                f"missing_templates={missing_templates}"
            )
        if not self.innovation.min_workers <= self.num_agents <= self.innovation.max_workers:
            raise InnovationConfigurationError(
                "initial parallel_agents is outside the adaptive worker bounds"
            )
        self.last_innovation_report: Dict[str, Any] = {}
        persisted = self.memory.get_last_topology_adjustment()
        if persisted:
            roles = persisted.get("report", {}).get("next_roles")
            if isinstance(roles, list) and roles:
                self._activate_next_roles([str(role) for role in roles])

    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:
        """Use exact worker templates instead of a generic decomposition model."""

        profiles = self.worker_profiles[:num_agents]
        return self.innovation.build_subtasks(user_input, profiles)

    def _activate_next_roles(self, roles: List[str]) -> None:
        if len(roles) != len(set(roles)):
            raise InnovationConfigurationError("next topology contains duplicate roles")
        if not self.innovation.min_workers <= len(roles) <= self.innovation.max_workers:
            raise InnovationConfigurationError(
                "next topology worker count is outside adaptive bounds"
            )
        unknown = [role for role in roles if role not in self.all_worker_profiles]
        if unknown:
            raise InnovationConfigurationError(
                f"next topology contains unknown roles: {unknown}"
            )
        selected = [self.all_worker_profiles[role] for role in roles]
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
