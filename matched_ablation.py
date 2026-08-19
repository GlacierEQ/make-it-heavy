# SPDX-License-Identifier: Proprietary
"""Bind causal worker metrics to real matched topology ablation executions.

The longitudinal memory layer already stores worker-level causal fields, but callers
previously had to populate them manually. This module closes that gap by admitting a
causal measurement only when an executed ABLATION mission is a strict one-worker
removal of its recorded parent experiment under the same mission family/comparison
key. The resulting measurement is written onto the parent worker metric that the live
portfolio selector already consumes.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from longitudinal_memory import LongitudinalAdaptiveSwarmMemory


class MatchedAblationError(ValueError):
    """Raised when an attempted causal promotion is not a matched execution."""


def _finite_unit(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise MatchedAblationError(f"{name} must be finite and between 0 and 1")
    return numeric


def _decode_topology(raw: str, label: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MatchedAblationError(f"{label} topology is not valid JSON") from exc
    if not isinstance(value, list) or not value:
        raise MatchedAblationError(f"{label} topology must be a non-empty role list")
    roles = [str(role).strip() for role in value]
    if any(not role for role in roles) or len(set(roles)) != len(roles):
        raise MatchedAblationError(f"{label} topology contains empty or duplicate roles")
    return roles


def _load_experiment(memory: LongitudinalAdaptiveSwarmMemory, mission_id: int) -> Dict[str, Any]:
    with memory._conn() as conn:
        row = conn.execute(
            """
            SELECT mission_id, mission_family, comparison_key, experiment_type,
                   parent_mission_id, freeze_topology, topology_json,
                   performance_valid, report_json
            FROM worker_experiments
            WHERE mission_id = ?
            """,
            (int(mission_id),),
        ).fetchone()
    if row is None:
        raise MatchedAblationError(f"no longitudinal experiment for mission={mission_id}")
    return dict(row)


def record_matched_worker_ablation(
    memory: LongitudinalAdaptiveSwarmMemory,
    ablated_mission_id: int,
    *,
    full_outcome_score: float,
    ablated_outcome_score: float,
    outcome_leverage: float,
    decision_changed: bool,
    details: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Promote one worker's causal value from a strict matched ablation execution.

    The child mission must already be persisted as an ABLATION experiment. Its topology
    must equal the parent topology minus exactly one worker, with no additions or role
    substitutions. Both experiments must be valid and share the same comparison
    identity. This prevents observational score history or loosely related reruns from
    being mislabeled as causal evidence.
    """

    full_score = _finite_unit(full_outcome_score, "full_outcome_score")
    ablated_score = _finite_unit(ablated_outcome_score, "ablated_outcome_score")
    leverage = _finite_unit(outcome_leverage, "outcome_leverage")

    child = _load_experiment(memory, int(ablated_mission_id))
    if str(child["experiment_type"]).upper() != "ABLATION":
        raise MatchedAblationError("child mission must be an ABLATION experiment")
    parent_id = child.get("parent_mission_id")
    if parent_id is None:
        raise MatchedAblationError("ABLATION experiment must identify parent_mission_id")
    if not bool(child["freeze_topology"]):
        raise MatchedAblationError("matched ABLATION requires freeze_topology=true")
    if not bool(child["performance_valid"]):
        raise MatchedAblationError("ablated execution is not performance-valid")

    parent = _load_experiment(memory, int(parent_id))
    if not bool(parent["performance_valid"]):
        raise MatchedAblationError("parent execution is not performance-valid")
    if str(parent["mission_family"]) != str(child["mission_family"]):
        raise MatchedAblationError("parent and ablation mission_family differ")
    if str(parent["comparison_key"]) != str(child["comparison_key"]):
        raise MatchedAblationError("parent and ablation comparison_key differ")

    parent_roles = _decode_topology(str(parent["topology_json"]), "parent")
    child_roles = _decode_topology(str(child["topology_json"]), "ablation")
    removed = sorted(set(parent_roles) - set(child_roles))
    added = sorted(set(child_roles) - set(parent_roles))
    if len(removed) != 1 or added:
        raise MatchedAblationError(
            "matched ABLATION must remove exactly one parent worker and add no roles"
        )
    removed_role = removed[0]

    with memory._conn() as conn:
        metric = conn.execute(
            """
            SELECT performance_valid
            FROM worker_longitudinal_metrics
            WHERE mission_id = ? AND agent_role = ?
            """,
            (int(parent_id), removed_role),
        ).fetchone()
    if metric is None or not bool(metric["performance_valid"]):
        raise MatchedAblationError(
            f"parent has no valid worker metric for removed role={removed_role}"
        )

    evidence = {
        "measurement_kind": "MATCHED_TOPOLOGY_ABLATION",
        "ablated_mission_id": int(ablated_mission_id),
        "mission_family": str(child["mission_family"]),
        "comparison_key": str(child["comparison_key"]),
        "parent_topology": parent_roles,
        "ablated_topology": child_roles,
    }
    if details:
        evidence["caller_details"] = dict(details)

    causal = memory.record_worker_ablation(
        int(parent_id),
        removed_role,
        full_outcome_score=full_score,
        ablated_outcome_score=ablated_score,
        outcome_leverage=leverage,
        decision_changed=bool(decision_changed),
        details=evidence,
    )
    return {
        "schema": "glaciereq.make-it-heavy.matched-worker-ablation.v1",
        "status": "CAUSAL_MEASUREMENT_RECORDED",
        "parent_mission_id": int(parent_id),
        "ablated_mission_id": int(ablated_mission_id),
        "removed_role": removed_role,
        "parent_topology": parent_roles,
        "ablated_topology": child_roles,
        "causal_measurement": causal,
        "truth_boundary": (
            "Causal value is recorded only for a performance-valid, same-family, "
            "same-comparison-key execution that removes exactly one worker."
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record one causal worker measurement from a matched ablation run"
    )
    parser.add_argument("db", type=Path, help="Longitudinal Make-It-Heavy SQLite database")
    parser.add_argument("ablated_mission_id", type=int, help="Persisted ABLATION mission id")
    parser.add_argument("--full-outcome", type=float, required=True)
    parser.add_argument("--ablated-outcome", type=float, required=True)
    parser.add_argument("--outcome-leverage", type=float, required=True)
    parser.add_argument("--decision-changed", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    memory = LongitudinalAdaptiveSwarmMemory(str(args.db))
    receipt = record_matched_worker_ablation(
        memory,
        args.ablated_mission_id,
        full_outcome_score=args.full_outcome,
        ablated_outcome_score=args.ablated_outcome,
        outcome_leverage=args.outcome_leverage,
        decision_changed=args.decision_changed,
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
