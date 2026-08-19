# SPDX-License-Identifier: Proprietary
"""Run ordinary adaptive missions with bounded, deterministic causal sampling.

The normal path executes exactly one production mission. On configured sample turns,
the same production orchestrator is passed through the proven matched-ablation runner,
which executes a baseline plus one exact worker removal and records causal value.
Mandatory evidence/proof roles are never selected for removal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol, Sequence

from adaptive_orchestrator import AdaptiveTaskOrchestrator
from matched_ablation_runner import execute_matched_worker_ablation

DEFAULT_PROTECTED_ROLES = frozenset(
    {"source_mapper", "adversarial_breaker", "proof_engineer"}
)


class CausalSamplingError(ValueError):
    """Raised when bounded causal sampling cannot be configured safely."""


class SamplingOrchestrator(Protocol):
    worker_profiles: list[dict[str, Any]]
    num_agents: int
    last_innovation_report: dict[str, Any]
    _current_mission_id: int
    memory: Any

    def orchestrate(self, user_input: str) -> str: ...


def should_sample(turn_index: int, every: int) -> bool:
    """Return whether this 1-based production turn is an ablation sample turn."""

    if turn_index <= 0:
        raise CausalSamplingError("turn_index must be positive")
    if every <= 0:
        raise CausalSamplingError("sample_every must be positive")
    return turn_index % every == 0


def select_removal_role(
    worker_profiles: Sequence[dict[str, Any]],
    *,
    turn_index: int,
    sample_every: int,
    protected_roles: frozenset[str] = DEFAULT_PROTECTED_ROLES,
) -> str | None:
    """Select an optional role deterministically while rotating sample coverage."""

    if not should_sample(turn_index, sample_every):
        return None
    roles = [str(profile.get("role") or "").strip() for profile in worker_profiles]
    if any(not role for role in roles):
        raise CausalSamplingError("active worker profile contains an empty role")
    if len(set(roles)) != len(roles):
        raise CausalSamplingError("active worker topology contains duplicate roles")

    removable = [role for role in roles if role not in protected_roles]
    if not removable:
        return None

    sample_ordinal = turn_index // sample_every - 1
    return removable[sample_ordinal % len(removable)]


def execute_bounded_causal_turn(
    orchestrator: SamplingOrchestrator,
    mission: str,
    *,
    turn_index: int,
    sample_every: int,
    mission_family: str,
    comparison_key: str,
    protected_roles: frozenset[str] = DEFAULT_PROTECTED_ROLES,
) -> dict[str, Any]:
    """Execute one normal turn or one bounded matched-ablation sample turn."""

    substantive_mission = str(mission).strip()
    family = str(mission_family).strip()
    key = str(comparison_key).strip()
    if not substantive_mission or not family or not key:
        raise CausalSamplingError(
            "mission, mission_family, and comparison_key are required"
        )

    remove_role = select_removal_role(
        orchestrator.worker_profiles,
        turn_index=turn_index,
        sample_every=sample_every,
        protected_roles=protected_roles,
    )
    if remove_role is None:
        synthesis = orchestrator.orchestrate(substantive_mission)
        return {
            "schema": "glaciereq.make-it-heavy.causal-sampling-runner.v1",
            "status": "NORMAL_TURN_EXECUTED",
            "turn_index": turn_index,
            "sample_every": sample_every,
            "sampled": False,
            "reason": (
                "turn_not_due"
                if not should_sample(turn_index, sample_every)
                else "no_removable_optional_role"
            ),
            "mission_id": int(orchestrator._current_mission_id),
            "synthesis": synthesis,
        }

    receipt = execute_matched_worker_ablation(
        orchestrator,
        substantive_mission,
        mission_family=family,
        comparison_key=key,
        remove_role=remove_role,
    )
    return {
        "schema": "glaciereq.make-it-heavy.causal-sampling-runner.v1",
        "status": "BOUNDED_CAUSAL_SAMPLE_EXECUTED",
        "turn_index": turn_index,
        "sample_every": sample_every,
        "sampled": True,
        "selected_removal_role": remove_role,
        "protected_roles": sorted(protected_roles),
        "matched_ablation": receipt,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Make-It-Heavy with bounded periodic matched-ablation sampling"
    )
    parser.add_argument("mission", type=Path, help="UTF-8 substantive mission file")
    parser.add_argument("--config", default="innovation_config.yaml")
    parser.add_argument("--turn-index", type=int, required=True)
    parser.add_argument("--sample-every", type=int, default=10)
    parser.add_argument("--mission-family", required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    mission = args.mission.read_text(encoding="utf-8")
    orchestrator = AdaptiveTaskOrchestrator(config_path=args.config, silent=True)
    receipt = execute_bounded_causal_turn(
        orchestrator,
        mission,
        turn_index=args.turn_index,
        sample_every=args.sample_every,
        mission_family=args.mission_family,
        comparison_key=args.comparison_key,
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
