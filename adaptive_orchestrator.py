# SPDX-License-Identifier: Proprietary
"""Innovation-stage orchestrator with per-turn worker scoring and adaptation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from health_memory import HealthAwareAdaptiveSwarmMemory
from innovation_health import (
    build_infrastructure_report,
    classify_local_capacity_contention,
    classify_shared_infrastructure_failure,
    mark_capacity_failures,
)
from innovation_loop import AdaptiveWorkerLoop, InnovationConfigurationError
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
        self.execution_parallelism = max(
            1,
            min(
                self.num_agents,
                int(innovation.get("execution_parallelism", self.num_agents)),
            ),
        )
        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")
        self.memory = HealthAwareAdaptiveSwarmMemory(memory_path)
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
            persisted_report = persisted.get("report", {})
            roles = persisted_report.get("next_roles")
            if isinstance(roles, list) and roles:
                self._activate_next_roles([str(role) for role in roles])
            next_parallel_width = persisted_report.get("next_parallel_width")
            if next_parallel_width is not None:
                self.execution_parallelism = max(
                    1, min(self.num_agents, int(next_parallel_width))
                )

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
        self.execution_parallelism = min(self.execution_parallelism, self.num_agents)

    def _persist_infrastructure_turn(
        self,
        user_input: str,
        incident: Dict[str, Any],
    ) -> Dict[str, Any]:
        report = build_infrastructure_report(
            self._current_mission_id,
            user_input,
            self.last_run_results,
            self.innovation,
            self.worker_profiles,
            incident,
        )
        self.memory.persist_adaptive_turn(
            self._current_mission_id,
            report["scores"],
            report["adjustments"],
            report["current_worker_count"],
            report["next_worker_count"],
            report["topology_reason"],
            report,
        )
        return report

    def orchestrate(self, user_input: str) -> str:
        """Execute, classify health, score valid output, persist, and tune next turn."""

        self._current_mission_id = self.memory.start_mission(user_input)
        try:
            synthesis = super().orchestrate(user_input)
            incident = classify_shared_infrastructure_failure(self.last_run_results)
            if incident is not None:
                report = self._persist_infrastructure_turn(user_input, incident)
                self.last_innovation_report = report
                final = f"{synthesis}\n\n{report['markdown']}"
                self.memory.complete_mission(
                    self._current_mission_id,
                    final,
                    status="infra_failed",
                )
                self._activate_next_roles(report["next_roles"])
                return final

            capacity_incident = classify_local_capacity_contention(
                self.last_run_results,
                base_url=self.config.get("openrouter", {}).get("base_url", ""),
                current_parallel_width=self.execution_parallelism,
            )
            effective_results = (
                mark_capacity_failures(self.last_run_results, capacity_incident)
                if capacity_incident is not None
                else self.last_run_results
            )
            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                effective_results,
                synthesis,
                current_parallel_width=self.execution_parallelism,
            )
            report["health_class"] = (
                "CAPACITY_CONTENTION"
                if capacity_incident is not None
                else "HEALTHY_OR_MIXED"
            )
            report["performance_valid"] = True
            if capacity_incident is not None:
                report["capacity"] = capacity_incident
            self.last_innovation_report = report
            final = f"{synthesis}\n\n{report['markdown']}"
            self.memory.complete_mission(
                self._current_mission_id,
                final,
                status="completed",
            )
            self._activate_next_roles(report["next_roles"])
            self.execution_parallelism = max(
                1,
                min(
                    self.num_agents,
                    int(report.get("next_parallel_width", self.execution_parallelism)),
                ),
            )
            return final
        except Exception:
            self.memory.complete_mission(
                self._current_mission_id,
                "Innovation turn failed before completion.",
                status="failed",
            )
            raise
