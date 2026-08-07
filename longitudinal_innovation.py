# SPDX-License-Identifier: Proprietary
"""Matched longitudinal experiments for adaptive worker-system science.

This layer deliberately stops treating the legacy `benefit_score` as causal value.
A mission can opt into an explicit experiment block.  In experiment mode:

* only mission-scoped template changes are injected;
* one change axis per changed worker is enforced;
* topology can be frozen to preserve comparability;
* structural quality remains separate from marginal system value and outcome leverage;
* causal values remain unknown until an ablation receipt is recorded.
"""

from __future__ import annotations

import json
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Sequence

from claim_aware_innovation import (
    CLAIM_CONTRACT,
    ClaimAwareAdaptiveWorkerLoop,
)
from innovation_loop import InnovationConfigurationError, WorkerTemplate


WORKER_EXPERIMENT_BEGIN = "WORKER_EXPERIMENT_BEGIN"
WORKER_EXPERIMENT_END = "WORKER_EXPERIMENT_END"
EXPERIMENT_TYPES = {"BASELINE", "TEMPLATE_DELTA", "ABLATION", "OBSERVATION"}

LONGITUDINAL_CONTRACT = """
LONGITUDINAL EXPERIMENT CONTRACT
1. Execute only this worker's assigned role; do not compensate for another worker.
2. Preserve material disagreement and failure. Do not optimize prose to raise a score.
3. A template change shown above is the only experimental instruction change for this worker.
4. Structural quality is not marginal system value. Do not claim that your own contribution
   changed the final outcome unless a separate counterfactual measurement establishes it.
5. Keep evidence, inference, proposal, and blocked states distinct so later ablation remains auditable.
""".strip()


class LongitudinalClaimAwareAdaptiveWorkerLoop(ClaimAwareAdaptiveWorkerLoop):
    """Claim-aware workers with explicit matched-turn experimental controls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._experiment_context: Optional[Dict[str, Any]] = None
        self._active_roles: List[str] = []

    @staticmethod
    def parse_experiment_context(mission: str) -> Optional[Dict[str, Any]]:
        """Parse one optional longitudinal experiment block from a mission."""

        begin_count = mission.count(WORKER_EXPERIMENT_BEGIN)
        end_count = mission.count(WORKER_EXPERIMENT_END)
        if begin_count == 0 and end_count == 0:
            return None
        if begin_count != 1 or end_count != 1:
            raise InnovationConfigurationError(
                "worker experiment requires exactly one begin marker and one end marker"
            )
        start = mission.find(WORKER_EXPERIMENT_BEGIN)
        end = mission.find(WORKER_EXPERIMENT_END)
        if start < 0 or end <= start:
            raise InnovationConfigurationError("malformed worker experiment markers")
        payload_text = mission[start + len(WORKER_EXPERIMENT_BEGIN) : end].strip()
        try:
            raw = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise InnovationConfigurationError(
                f"malformed worker experiment JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise InnovationConfigurationError("worker experiment must be a JSON object")

        mission_family = str(raw.get("mission_family") or "").strip()
        comparison_key = str(raw.get("comparison_key") or "").strip()
        experiment_type = str(raw.get("experiment_type") or "").upper().strip()
        if not mission_family or not comparison_key:
            raise InnovationConfigurationError(
                "worker experiment requires mission_family and comparison_key"
            )
        if experiment_type not in EXPERIMENT_TYPES:
            raise InnovationConfigurationError(
                f"unsupported worker experiment type: {experiment_type!r}"
            )

        raw_changes = raw.get("template_changes") or []
        if not isinstance(raw_changes, list):
            raise InnovationConfigurationError("template_changes must be a list")
        changes: List[Dict[str, Any]] = []
        seen_roles = set()
        seen_change_ids = set()
        for index, raw_change in enumerate(raw_changes):
            if not isinstance(raw_change, dict):
                raise InnovationConfigurationError(
                    f"template_changes[{index}] must be an object"
                )
            role = str(raw_change.get("role") or "").strip()
            change_id = str(raw_change.get("change_id") or "").strip()
            change_axis = str(raw_change.get("change_axis") or "").strip()
            instruction = str(raw_change.get("instruction") or "").strip()
            hypothesis = str(raw_change.get("hypothesis") or "").strip()
            if not all((role, change_id, change_axis, instruction, hypothesis)):
                raise InnovationConfigurationError(
                    f"template_changes[{index}] requires role, change_id, change_axis, "
                    "instruction, and hypothesis"
                )
            if role in seen_roles:
                raise InnovationConfigurationError(
                    f"only one changed variable is allowed per worker per turn: {role}"
                )
            if change_id in seen_change_ids:
                raise InnovationConfigurationError(
                    f"duplicate worker change_id: {change_id}"
                )
            seen_roles.add(role)
            seen_change_ids.add(change_id)
            changes.append(
                {
                    "role": role,
                    "change_id": change_id,
                    "change_axis": change_axis,
                    "instruction": instruction,
                    "hypothesis": hypothesis,
                }
            )

        if experiment_type == "BASELINE" and changes:
            raise InnovationConfigurationError(
                "BASELINE experiments cannot include template_changes"
            )
        if experiment_type == "TEMPLATE_DELTA" and not changes:
            raise InnovationConfigurationError(
                "TEMPLATE_DELTA experiments require at least one template change"
            )
        parent_mission_id = raw.get("parent_mission_id")
        if experiment_type in {"TEMPLATE_DELTA", "ABLATION"} and parent_mission_id is None:
            raise InnovationConfigurationError(
                f"{experiment_type} experiments require parent_mission_id"
            )
        if parent_mission_id is not None:
            try:
                parent_mission_id = int(parent_mission_id)
            except (TypeError, ValueError) as exc:
                raise InnovationConfigurationError(
                    "parent_mission_id must be an integer"
                ) from exc
            if parent_mission_id <= 0:
                raise InnovationConfigurationError(
                    "parent_mission_id must be positive"
                )

        return {
            "schema": "glaciereq.make-it-heavy.worker-experiment.v1",
            "mission_family": mission_family,
            "comparison_key": comparison_key,
            "experiment_type": experiment_type,
            "parent_mission_id": parent_mission_id,
            "freeze_topology": bool(raw.get("freeze_topology", True)),
            "template_changes": changes,
            "hypothesis": str(raw.get("hypothesis") or "").strip() or None,
        }

    @staticmethod
    def mission_without_experiment_block(mission: str) -> str:
        """Remove controller metadata before handing the substantive mission to workers."""

        if WORKER_EXPERIMENT_BEGIN not in mission and WORKER_EXPERIMENT_END not in mission:
            return mission
        start = mission.find(WORKER_EXPERIMENT_BEGIN)
        end = mission.find(WORKER_EXPERIMENT_END)
        if start < 0 or end <= start:
            return mission
        tail = end + len(WORKER_EXPERIMENT_END)
        return f"{mission[:start]}\n{mission[tail:]}".strip()

    def build_subtasks(
        self,
        mission: str,
        worker_profiles: Sequence[Mapping[str, Any]],
    ) -> List[str]:
        """Build experiment-isolated tasks and reject hidden cross-turn prompt drift."""

        context = self.parse_experiment_context(mission)
        self._experiment_context = context
        self._active_roles = [str(profile["role"]) for profile in worker_profiles]
        if context is None:
            return super().build_subtasks(mission, worker_profiles)

        unknown_changes = sorted(
            {
                str(change["role"])
                for change in context["template_changes"]
                if str(change["role"]) not in self.templates_by_role
            }
        )
        if unknown_changes:
            raise InnovationConfigurationError(
                f"template change references unknown worker roles: {unknown_changes}"
            )
        active_set = set(self._active_roles)
        inactive_changes = sorted(
            str(change["role"])
            for change in context["template_changes"]
            if str(change["role"]) not in active_set
        )
        if inactive_changes:
            raise InnovationConfigurationError(
                f"template change references inactive worker roles: {inactive_changes}"
            )

        substantive_mission = self.mission_without_experiment_block(mission)
        self._evidence_registry = self.parse_evidence_registry(substantive_mission)
        changes_by_role = {
            str(change["role"]): dict(change)
            for change in context["template_changes"]
        }
        tasks: List[str] = []
        for template in self.active_templates(worker_profiles):
            change = changes_by_role.get(template.role)
            if change is None:
                runtime_adjustment = (
                    "NEXT-TURN TEMPLATE ADJUSTMENT:\n"
                    "None. Preserve this worker's baseline contract for the experiment."
                )
            else:
                runtime_adjustment = (
                    "NEXT-TURN TEMPLATE ADJUSTMENT — ONE VARIABLE ONLY:\n"
                    f"change_id={change['change_id']}\n"
                    f"change_axis={change['change_axis']}\n"
                    f"instruction={change['instruction']}\n"
                    f"hypothesis={change['hypothesis']}"
                )
            task = template.task_template.format(
                mission=substantive_mission,
                runtime_adjustment=runtime_adjustment,
            ).strip()
            tasks.append(f"{task}\n\n{CLAIM_CONTRACT}\n\n{LONGITUDINAL_CONTRACT}")
        return tasks

    def _next_worker_count(
        self,
        current_count: int,
        scores: Sequence[Mapping[str, Any]],
    ) -> tuple[int, str]:
        context = self._experiment_context
        if context is not None and bool(context.get("freeze_topology")):
            return (
                current_count,
                "Hold topology: matched longitudinal experiment freezes worker composition.",
            )
        return super()._next_worker_count(current_count, scores)

    def _next_roles(
        self,
        scores: Sequence[Mapping[str, Any]],
        next_count: int,
    ) -> List[str]:
        context = self._experiment_context
        if context is not None and bool(context.get("freeze_topology")):
            roles = [str(score["role"]) for score in scores]
            if len(roles) != next_count:
                raise InnovationConfigurationError(
                    "frozen topology count does not match worker score count"
                )
            return roles
        return super()._next_roles(scores, next_count)

    @staticmethod
    def _telemetry_markdown(
        context: Mapping[str, Any],
        longitudinal: Mapping[str, Any],
        report: Mapping[str, Any],
    ) -> str:
        metrics = list(longitudinal.get("metrics") or [])
        reviewable = [row for row in metrics if row.get("performance_valid")]
        completed = len(reviewable)
        quality_values = [float(row["quality"]) for row in reviewable]
        heuristic_values = [float(row["heuristic_benefit"]) for row in reviewable]
        highest = (
            max(reviewable, key=lambda row: float(row["quality"]))
            if reviewable
            else None
        )
        lowest = (
            min(reviewable, key=lambda row: float(row["quality"]))
            if reviewable
            else None
        )
        applied = [
            f"{change['role']}:{change['change_axis']} ({change['change_id']})"
            for change in context.get("template_changes") or []
        ]
        predecessor_count = sum(
            1 for row in reviewable if row.get("predecessor_mission_id") is not None
        )
        lines = [
            "## LONGITUDINAL WORKER TELEMETRY",
            "",
            f"Experiment: {context['experiment_type']}",
            f"Mission family: {context['mission_family']}",
            f"Comparison key: {context['comparison_key']}",
            f"Workers started: {len(metrics)}",
            f"Workers completed with reviewable inference: {completed}",
            f"Workers non-reviewable: {len(metrics) - completed}",
            "Workers causally useful: NOT YET MEASURED",
            "Workers causally redundant: NOT YET MEASURED",
            f"Average quality: {mean(quality_values):.2f}" if quality_values else "Average quality: N/A",
            (
                f"Average heuristic benefit: {mean(heuristic_values):.4f}"
                if heuristic_values
                else "Average heuristic benefit: N/A"
            ),
            "Average marginal system value: PENDING ABLATION",
            "Outcome leverage: PENDING ABLATION",
            f"Comparable predecessor rows: {predecessor_count}/{completed}",
            (
                f"Highest structural quality: {highest['role']} ({float(highest['quality']):.2f})"
                if highest
                else "Highest structural quality: N/A"
            ),
            (
                f"Lowest structural quality: {lowest['role']} ({float(lowest['quality']):.2f})"
                if lowest
                else "Lowest structural quality: N/A"
            ),
            f"Applied template changes: {', '.join(applied) if applied else 'none'}",
            (
                "Topology: HOLD "
                f"{report['current_worker_count']} -> {report['next_worker_count']} workers"
                if bool(context.get("freeze_topology"))
                else (
                    "Topology: "
                    f"{report['current_worker_count']} -> {report['next_worker_count']} workers"
                )
            ),
            (
                f"Hypothesis: {context['hypothesis']}"
                if context.get("hypothesis")
                else "Hypothesis: none registered"
            ),
            "",
            "Truth boundary: quality and heuristic benefit are observational worker scores. "
            "Marginal system value and outcome leverage are intentionally absent until a "
            "counterfactual full-vs-ablated measurement is recorded.",
        ]
        return "\n".join(lines)

    def evaluate_turn(
        self,
        mission_id: int,
        mission: str,
        results: Sequence[Mapping[str, Any]],
        synthesis: str,
    ) -> Dict[str, Any]:
        """Run legacy structural scoring, then add matched causal-ready telemetry."""

        report = super().evaluate_turn(mission_id, mission, results, synthesis)
        context = self._experiment_context
        if context is None:
            report["score_semantics"] = {
                "quality_score": "structural worker quality",
                "benefit_score": "legacy heuristic benefit; not causal marginal value",
            }
            return report

        if self.memory is None or not hasattr(self.memory, "persist_longitudinal_turn"):
            raise InnovationConfigurationError(
                "longitudinal experiment requires LongitudinalAdaptiveSwarmMemory"
            )
        report["legacy_heuristic_benefit"] = report.get("average_benefit")
        report["average_marginal_system_value"] = None
        report["outcome_leverage"] = None
        report["score_semantics"] = {
            "quality_score": (
                "Worker execution quality for its assigned contract, including active "
                "claim/evidence gates."
            ),
            "benefit_score": (
                "Legacy heuristic only. It mixes uniqueness, completion, quality, and speed; "
                "it is not marginal system value."
            ),
            "marginal_system_value": (
                "Signed full-swarm minus worker-ablated outcome delta; unmeasured until ablation."
            ),
            "outcome_leverage": (
                "Independent normalized magnitude of decision/architecture/artifact change; "
                "unmeasured until ablation."
            ),
        }
        longitudinal = self.memory.persist_longitudinal_turn(
            mission_id,
            context,
            [dict(score) for score in report["scores"]],
            list(self._active_roles),
            report,
        )
        report["longitudinal"] = longitudinal
        telemetry = self._telemetry_markdown(context, longitudinal, report)
        legacy_markdown = str(report.get("markdown") or "").replace(
            "average marginal benefit", "average heuristic benefit"
        )
        report["markdown"] = f"{legacy_markdown}\n\n{telemetry}".strip()
        self.last_report = report
        return report
