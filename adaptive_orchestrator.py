# SPDX-License-Identifier: Proprietary
"""Health-aware adaptive orchestration with bounded provider concurrency."""

from __future__ import annotations

import logging
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from math import ceil
from pathlib import Path
from typing import Any, Dict, List

from health_memory import HealthAwareAdaptiveSwarmMemory
from innovation_health import (
    build_infrastructure_report,
    classify_shared_infrastructure_failure,
)
from innovation_loop import InnovationConfigurationError
from orchestrator import (
    RESULT_CLASSIFICATION,
    REVIEW_STATUS,
    STATUS_QUEUED,
    STATUS_TIMEOUT,
    TaskOrchestrator,
)
from semantic_claim_innovation import SemanticClaimAdaptiveWorkerLoop

logger = logging.getLogger(__name__)


def bounded_provider_concurrency(logical_workers: int, configured_width: int) -> int:
    """Bound provider concurrency independently from logical worker count."""

    logical = max(1, int(logical_workers))
    width = max(1, int(configured_width))
    return min(logical, width)


def effective_turn_timeout(
    task_timeout: float,
    logical_workers: int,
    provider_width: int,
) -> float:
    """Scale the turn budget by execution waves when provider width is narrower."""

    width = bounded_provider_concurrency(logical_workers, provider_width)
    waves = max(1, ceil(max(1, int(logical_workers)) / width))
    return float(task_timeout) * waves


class AdaptiveTaskOrchestrator(TaskOrchestrator):
    """Execute, health-classify, score, persist, and adapt worker turns."""

    def __init__(
        self,
        config_path: str = "innovation_config.yaml",
        silent: bool = False,
    ) -> None:
        super().__init__(config_path=config_path, silent=silent)
        innovation = self.config.get("innovation", {})
        memory_path = self.config.get("memory", {}).get("db_path", ".swarm_memory.db")
        self.memory = HealthAwareAdaptiveSwarmMemory(memory_path)
        template_path = Path(config_path).resolve().parent / innovation.get(
            "template_path",
            "templates/innovation_workers.yaml",
        )
        self.provider_concurrency_width = max(
            1,
            int(innovation.get("provider_concurrency_width", self.num_agents)),
        )
        self.innovation = SemanticClaimAdaptiveWorkerLoop(
            template_path,
            self.memory,
            min_workers=int(innovation.get("min_workers", 4)),
            max_workers=int(innovation.get("max_workers", 8)),
            target_quality=float(innovation.get("target_quality", 78.0)),
            target_benefit=float(innovation.get("target_benefit", 0.60)),
            claim_gate_min_score=float(innovation.get("claim_gate_min_score", 0.75)),
            claim_gate_quality_cap=float(
                innovation.get("claim_gate_quality_cap", 69.0)
            ),
            semantic_gate_quality_cap=float(
                innovation.get("semantic_gate_quality_cap", 59.0)
            ),
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
        self.worker_profiles = [self.all_worker_profiles[role] for role in roles]
        self.num_agents = len(self.worker_profiles)

    def _run_bounded_worker_set(self, user_input: str) -> str:
        """Execute logical workers while independently bounding provider concurrency."""

        with self.progress_lock:
            self.agent_progress = {}
            self.agent_results = {}
        subtasks = self.decompose_task(user_input, self.num_agents)
        for index in range(self.num_agents):
            self.update_agent_progress(index, STATUS_QUEUED)

        provider_width = bounded_provider_concurrency(
            self.num_agents,
            self.provider_concurrency_width,
        )
        turn_timeout = effective_turn_timeout(
            self.task_timeout,
            self.num_agents,
            provider_width,
        )
        executor = ThreadPoolExecutor(max_workers=provider_width)
        futures = {
            executor.submit(self.run_agent_parallel, index, subtasks[index]): index
            for index in range(self.num_agents)
        }
        results: List[Dict[str, Any]] = []
        completed = set()
        try:
            for future in as_completed(futures, timeout=turn_timeout):
                agent_id = futures[future]
                completed.add(agent_id)
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(self._future_error(agent_id, exc))
        except FuturesTimeoutError:
            logger.warning(
                "Bounded adaptive turn timeout reached after %.1fs "
                "(%d logical workers / provider width %d)",
                turn_timeout,
                self.num_agents,
                provider_width,
            )
        finally:
            for future, agent_id in futures.items():
                if agent_id in completed:
                    continue
                cancelled = future.cancel()
                self.update_agent_progress(agent_id, STATUS_TIMEOUT)
                profile = self.worker_profiles[agent_id]
                results.append(
                    {
                        "agent_id": agent_id,
                        "role": profile["role"],
                        "model": profile["model"],
                        "status": "timeout",
                        "result_classification": RESULT_CLASSIFICATION,
                        "review_status": REVIEW_STATUS,
                        "response": (
                            f"Worker exceeded the {turn_timeout:g}s adaptive turn timeout"
                        ),
                        "execution_time": turn_timeout,
                        "cancelled_before_start": cancelled,
                    }
                )
            executor.shutdown(wait=False, cancel_futures=True)

        results.sort(key=lambda item: item["agent_id"])
        self.last_run_results = results
        return self.aggregate_results(results)

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
        report["provider_concurrency_width"] = bounded_provider_concurrency(
            self.num_agents,
            self.provider_concurrency_width,
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
        """Run one turn without letting shared infrastructure poison prompt learning."""

        self._current_mission_id = self.memory.start_mission(user_input)
        try:
            synthesis = self._run_bounded_worker_set(user_input)
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

            report = self.innovation.evaluate_turn(
                self._current_mission_id,
                user_input,
                self.last_run_results,
                synthesis,
            )
            report["health_class"] = "HEALTHY_OR_MIXED"
            report["performance_valid"] = True
            report["provider_concurrency_width"] = bounded_provider_concurrency(
                self.num_agents,
                self.provider_concurrency_width,
            )
            report["claim_gate_pass_rate"] = round(
                sum(
                    1
                    for score in report["scores"]
                    if score.get("claim_gate", {}).get("pass")
                )
                / max(1, len(report["scores"])),
                4,
            )
            semantic_applicable = [
                score.get("semantic_claim_gate", {})
                for score in report["scores"]
                if score.get("semantic_claim_gate", {}).get("applicable")
            ]
            report["semantic_claim_gate_pass_rate"] = (
                round(
                    sum(1 for gate in semantic_applicable if gate.get("pass"))
                    / len(semantic_applicable),
                    4,
                )
                if semantic_applicable
                else None
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
