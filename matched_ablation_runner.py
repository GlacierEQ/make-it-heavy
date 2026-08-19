# SPDX-License-Identifier: Proprietary
"""Execute a full swarm and one-worker matched ablation under one outcome rubric.

This module closes the final causal-learning gap in the adaptive worker stack.  It does
not infer causality from observational history.  Instead it executes two real adaptive
missions against the same mission family/comparison key, freezes both topologies,
removes exactly one worker from the second execution, evaluates both completed runs
with the same deterministic system-level rubric, and only then delegates causal
promotion to :mod:`matched_ablation`.

The CLI uses :class:`AdaptiveTaskOrchestrator`, so production execution still exercises
real provider-backed workers.  Tests may inject an orchestrator implementing the same
small protocol, but no simulated execution path is exposed by the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from matched_ablation import record_matched_worker_ablation


class MatchedAblationRunnerError(ValueError):
    """Raised when a full/ablated experiment pair cannot be executed safely."""


class ExperimentOrchestrator(Protocol):
    """Minimal production contract consumed by the matched-ablation runner."""

    worker_profiles: list[dict[str, Any]]
    num_agents: int
    last_innovation_report: dict[str, Any]
    _current_mission_id: int
    memory: Any

    def orchestrate(self, user_input: str) -> str: ...


@dataclass(frozen=True)
class OutcomeEvaluation:
    """One normalized system outcome under the shared experiment rubric."""

    score: float
    band: str
    completion_rate: float
    average_quality: float
    claim_gate_pass_rate: float
    semantic_claim_gate_pass_rate: float
    synthesis_sha256: str


@dataclass(frozen=True)
class ExperimentExecution:
    """Observed execution facts needed for matched causal promotion."""

    mission_id: int
    roles: tuple[str, ...]
    synthesis: str
    report: Mapping[str, Any]
    outcome: OutcomeEvaluation


def _finite_unit(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise MatchedAblationRunnerError(f"{name} must be finite and between 0 and 1")
    return numeric


def _normalized_gate(value: Any) -> float:
    if value is None:
        return 1.0
    return _finite_unit(float(value), "gate pass rate")


def evaluate_system_outcome(
    report: Mapping[str, Any],
    synthesis: str,
) -> OutcomeEvaluation:
    """Score the completed system run without reusing per-worker causal fields.

    The rubric intentionally operates at the whole-run boundary.  It combines worker
    completion, aggregate structural quality, claim-gate pass rate, and semantic-gate
    pass rate.  These four observables are measured identically for the full and
    ablated executions.  The resulting full-minus-ablated delta is therefore a causal
    effect *with respect to this explicit rubric*, not a claim of universal worker
    usefulness.
    """

    scores = list(report.get("scores") or [])
    if not scores:
        raise MatchedAblationRunnerError("experiment report contains no worker scores")

    completed = sum(
        1 for row in scores if str(row.get("runtime_status")) == "model_inference"
    )
    completion_rate = completed / len(scores)
    quality_values = [
        float(row.get("quality_score") or 0.0) / 100.0
        for row in scores
        if str(row.get("runtime_status")) == "model_inference"
    ]
    average_quality = sum(quality_values) / len(quality_values) if quality_values else 0.0
    average_quality = _finite_unit(average_quality, "average quality")

    claim_rate = _normalized_gate(report.get("claim_gate_pass_rate"))
    semantic_rate = _normalized_gate(report.get("semantic_claim_gate_pass_rate"))
    score = round(
        0.35 * completion_rate
        + 0.35 * average_quality
        + 0.15 * claim_rate
        + 0.15 * semantic_rate,
        4,
    )
    score = _finite_unit(score, "system outcome score")
    band = "STRONG" if score >= 0.80 else "VIABLE" if score >= 0.60 else "WEAK"
    synthesis_sha256 = hashlib.sha256(synthesis.encode("utf-8")).hexdigest()
    return OutcomeEvaluation(
        score=score,
        band=band,
        completion_rate=round(completion_rate, 4),
        average_quality=round(average_quality, 4),
        claim_gate_pass_rate=round(claim_rate, 4),
        semantic_claim_gate_pass_rate=round(semantic_rate, 4),
        synthesis_sha256=synthesis_sha256,
    )


def _experiment_block(payload: Mapping[str, Any]) -> str:
    return (
        "WORKER_EXPERIMENT_BEGIN\n"
        f"{json.dumps(dict(payload), sort_keys=True)}\n"
        "WORKER_EXPERIMENT_END"
    )


def _mission_with_experiment(
    mission: str,
    *,
    mission_family: str,
    comparison_key: str,
    experiment_type: str,
    parent_mission_id: int | None = None,
) -> str:
    payload: dict[str, Any] = {
        "mission_family": mission_family,
        "comparison_key": comparison_key,
        "experiment_type": experiment_type,
        "freeze_topology": True,
        "template_changes": [],
    }
    if parent_mission_id is not None:
        payload["parent_mission_id"] = int(parent_mission_id)
    return f"{_experiment_block(payload)}\n\n{mission.strip()}"


def _profile_roles(orchestrator: ExperimentOrchestrator) -> list[str]:
    roles = [str(profile.get("role") or "").strip() for profile in orchestrator.worker_profiles]
    if not roles or any(not role for role in roles):
        raise MatchedAblationRunnerError("active worker profiles contain an empty role")
    if len(set(roles)) != len(roles):
        raise MatchedAblationRunnerError("active worker topology contains duplicate roles")
    return roles


def _execute_one(
    orchestrator: ExperimentOrchestrator,
    mission: str,
) -> ExperimentExecution:
    roles_before = tuple(_profile_roles(orchestrator))
    synthesis = orchestrator.orchestrate(mission)
    mission_id = int(orchestrator._current_mission_id)
    report = dict(orchestrator.last_innovation_report)
    if mission_id <= 0:
        raise MatchedAblationRunnerError("orchestrator did not expose a persisted mission id")
    if not report:
        raise MatchedAblationRunnerError("orchestrator did not expose an innovation report")
    outcome = evaluate_system_outcome(report, synthesis)
    return ExperimentExecution(
        mission_id=mission_id,
        roles=roles_before,
        synthesis=synthesis,
        report=report,
        outcome=outcome,
    )


def execute_matched_worker_ablation(
    orchestrator: ExperimentOrchestrator,
    mission: str,
    *,
    mission_family: str,
    comparison_key: str,
    remove_role: str,
) -> dict[str, Any]:
    """Execute and causally promote one full-vs-ablated worker experiment pair."""

    family = str(mission_family).strip()
    key = str(comparison_key).strip()
    removed = str(remove_role).strip()
    substantive_mission = str(mission).strip()
    if not family or not key or not removed or not substantive_mission:
        raise MatchedAblationRunnerError(
            "mission, mission_family, comparison_key, and remove_role are required"
        )

    full_roles = _profile_roles(orchestrator)
    if removed not in full_roles:
        raise MatchedAblationRunnerError(f"remove_role is not active: {removed}")
    if len(full_roles) <= 1:
        raise MatchedAblationRunnerError("matched ablation requires at least two workers")

    full_mission = _mission_with_experiment(
        substantive_mission,
        mission_family=family,
        comparison_key=key,
        experiment_type="BASELINE",
    )
    full = _execute_one(orchestrator, full_mission)

    ablated_profiles = [
        dict(profile)
        for profile in orchestrator.worker_profiles
        if str(profile.get("role")) != removed
    ]
    if len(ablated_profiles) != len(full_roles) - 1:
        raise MatchedAblationRunnerError(
            "failed to derive an exact one-worker-removed topology"
        )
    orchestrator.worker_profiles = ablated_profiles
    orchestrator.num_agents = len(ablated_profiles)

    ablated_mission = _mission_with_experiment(
        substantive_mission,
        mission_family=family,
        comparison_key=key,
        experiment_type="ABLATION",
        parent_mission_id=full.mission_id,
    )
    ablated = _execute_one(orchestrator, ablated_mission)

    expected_ablated = [role for role in full.roles if role != removed]
    if list(ablated.roles) != expected_ablated:
        raise MatchedAblationRunnerError(
            "ablated execution topology drifted from exact parent-minus-one ordering"
        )

    decision_changed = full.outcome.band != ablated.outcome.band
    outcome_leverage = round(abs(full.outcome.score - ablated.outcome.score), 4)
    causal = record_matched_worker_ablation(
        orchestrator.memory,
        ablated.mission_id,
        full_outcome_score=full.outcome.score,
        ablated_outcome_score=ablated.outcome.score,
        outcome_leverage=outcome_leverage,
        decision_changed=decision_changed,
        details={
            "runner": "matched_ablation_runner.execute_matched_worker_ablation",
            "rubric": "SYSTEM_EVIDENCE_QUALITY_V1",
            "full_outcome": full.outcome.__dict__,
            "ablated_outcome": ablated.outcome.__dict__,
        },
    )

    return {
        "schema": "glaciereq.make-it-heavy.matched-ablation-runner.v1",
        "status": "MATCHED_ABLATION_EXECUTED_AND_RECORDED",
        "mission_family": family,
        "comparison_key": key,
        "removed_role": removed,
        "full": {
            "mission_id": full.mission_id,
            "roles": list(full.roles),
            "outcome": full.outcome.__dict__,
        },
        "ablated": {
            "mission_id": ablated.mission_id,
            "roles": list(ablated.roles),
            "outcome": ablated.outcome.__dict__,
        },
        "decision_changed": decision_changed,
        "outcome_leverage": outcome_leverage,
        "causal_measurement": causal,
        "truth_boundary": (
            "Causal value is the observed full-minus-ablated effect under the identical "
            "SYSTEM_EVIDENCE_QUALITY_V1 rubric for a persisted exact one-worker removal."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute a full Make-It-Heavy mission plus one-worker matched ablation"
    )
    parser.add_argument("mission", type=Path, help="UTF-8 substantive mission file")
    parser.add_argument("--config", default="innovation_config.yaml")
    parser.add_argument("--mission-family", required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--remove-role", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    mission = args.mission.read_text(encoding="utf-8")
    orchestrator = AdaptiveTaskOrchestrator(config_path=args.config, silent=True)
    receipt = execute_matched_worker_ablation(
        orchestrator,
        mission,
        mission_family=args.mission_family,
        comparison_key=args.comparison_key,
        remove_role=args.remove_role,
    )
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
