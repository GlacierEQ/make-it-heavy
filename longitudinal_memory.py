# SPDX-License-Identifier: Proprietary
"""Longitudinal experiment storage for causal worker-system learning.

The legacy adaptive tables remain intact for backwards compatibility.  This layer
adds matched mission-family experiments, separates structural quality from causal
marginal system value and outcome leverage, and stores worker-ablation receipts.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, List, Mapping, Optional

from health_memory import HealthAwareAdaptiveSwarmMemory


EXPERIMENT_TYPES = {"BASELINE", "TEMPLATE_DELTA", "ABLATION", "OBSERVATION"}


def _finite_unit(value: float, name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")
    return numeric


class LongitudinalAdaptiveSwarmMemory(HealthAwareAdaptiveSwarmMemory):
    """Persist matched worker experiments without conflating score semantics."""

    def _init_db(self) -> None:
        super()._init_db()
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS worker_experiments (
                    mission_id INTEGER PRIMARY KEY,
                    mission_family TEXT NOT NULL,
                    comparison_key TEXT NOT NULL,
                    experiment_type TEXT NOT NULL,
                    parent_mission_id INTEGER,
                    freeze_topology INTEGER NOT NULL,
                    topology_json TEXT NOT NULL,
                    change_set_json TEXT NOT NULL,
                    performance_valid INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id),
                    FOREIGN KEY(parent_mission_id) REFERENCES missions(id)
                );
                CREATE TABLE IF NOT EXISTS worker_longitudinal_metrics (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER NOT NULL,
                    agent_role TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    change_id TEXT,
                    change_axis TEXT,
                    quality_score REAL NOT NULL,
                    heuristic_benefit_score REAL NOT NULL,
                    unique_contribution_score REAL NOT NULL,
                    overlap_signal REAL NOT NULL,
                    execution_time REAL NOT NULL,
                    marginal_system_value REAL,
                    outcome_leverage REAL,
                    predecessor_mission_id INTEGER,
                    quality_delta REAL,
                    marginal_value_delta REAL,
                    leverage_delta REAL,
                    performance_valid INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(mission_id, agent_role),
                    FOREIGN KEY(mission_id) REFERENCES missions(id),
                    FOREIGN KEY(predecessor_mission_id) REFERENCES missions(id)
                );
                CREATE TABLE IF NOT EXISTS worker_ablations (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER NOT NULL,
                    agent_role TEXT NOT NULL,
                    full_outcome_score REAL NOT NULL,
                    ablated_outcome_score REAL NOT NULL,
                    marginal_system_value REAL NOT NULL,
                    outcome_leverage REAL NOT NULL,
                    decision_changed INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(mission_id, agent_role),
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_worker_experiments_family
                    ON worker_experiments(mission_family, comparison_key, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_worker_longitudinal_role
                    ON worker_longitudinal_metrics(agent_role, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_worker_longitudinal_mission
                    ON worker_longitudinal_metrics(mission_id);
                CREATE INDEX IF NOT EXISTS idx_worker_ablations_mission
                    ON worker_ablations(mission_id);
                """
            )

    def find_comparable_predecessor(
        self,
        role: str,
        mission_family: str,
        comparison_key: str,
        *,
        before_mission_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the latest valid same-family/same-key measurement for one role."""

        params: List[Any] = [str(role), str(mission_family), str(comparison_key)]
        before_clause = ""
        if before_mission_id is not None:
            before_clause = "AND metric.mission_id <> ?"
            params.append(int(before_mission_id))
        with self._conn() as conn:
            row = conn.execute(
                f"""
                SELECT metric.*, experiment.experiment_type,
                       experiment.mission_family, experiment.comparison_key
                FROM worker_longitudinal_metrics AS metric
                JOIN worker_experiments AS experiment
                  ON experiment.mission_id = metric.mission_id
                WHERE metric.agent_role = ?
                  AND experiment.mission_family = ?
                  AND experiment.comparison_key = ?
                  AND metric.performance_valid = 1
                  AND experiment.performance_valid = 1
                  {before_clause}
                ORDER BY metric.id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        return dict(row) if row is not None else None

    def persist_longitudinal_turn(
        self,
        mission_id: int,
        context: Mapping[str, Any],
        scores: List[Dict[str, Any]],
        active_roles: List[str],
        report: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Persist one matched experiment and independent per-worker metrics.

        `benefit_score` is intentionally stored as `heuristic_benefit_score`.
        Causal marginal system value and outcome leverage remain NULL until an
        ablation or another explicit counterfactual measurement records them.
        """

        mission_family = str(context["mission_family"]).strip()
        comparison_key = str(context["comparison_key"]).strip()
        experiment_type = str(context["experiment_type"]).upper().strip()
        if not mission_family or not comparison_key:
            raise ValueError("mission_family and comparison_key are required")
        if experiment_type not in EXPERIMENT_TYPES:
            raise ValueError(f"unsupported experiment_type: {experiment_type}")

        changes = context.get("template_changes") or []
        if not isinstance(changes, list):
            raise ValueError("template_changes must be a list")
        changes_by_role = {
            str(change["role"]): dict(change)
            for change in changes
            if isinstance(change, Mapping) and change.get("role")
        }
        parent_mission_id = context.get("parent_mission_id")
        freeze_topology = bool(context.get("freeze_topology", True))
        created_at = time.time()
        experiment_valid = bool(scores) and all(
            str(score.get("runtime_status")) == "model_inference" for score in scores
        )

        metric_rows: List[Dict[str, Any]] = []
        with self._conn() as conn:
            self._assert_mission_exists(conn, mission_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO worker_experiments (
                    mission_id, mission_family, comparison_key, experiment_type,
                    parent_mission_id, freeze_topology, topology_json,
                    change_set_json, performance_valid, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(mission_id),
                    mission_family,
                    comparison_key,
                    experiment_type,
                    int(parent_mission_id) if parent_mission_id is not None else None,
                    int(freeze_topology),
                    json.dumps(list(active_roles), sort_keys=True),
                    json.dumps(changes, sort_keys=True),
                    int(experiment_valid),
                    json.dumps(dict(report), sort_keys=True),
                    created_at,
                ),
            )

            for score in scores:
                role = str(score["role"])
                predecessor = conn.execute(
                    """
                    SELECT metric.*
                    FROM worker_longitudinal_metrics AS metric
                    JOIN worker_experiments AS experiment
                      ON experiment.mission_id = metric.mission_id
                    WHERE metric.agent_role = ?
                      AND experiment.mission_family = ?
                      AND experiment.comparison_key = ?
                      AND metric.performance_valid = 1
                      AND experiment.performance_valid = 1
                      AND metric.mission_id <> ?
                    ORDER BY metric.id DESC
                    LIMIT 1
                    """,
                    (role, mission_family, comparison_key, int(mission_id)),
                ).fetchone()
                quality = float(score["quality_score"])
                heuristic_benefit = float(score["benefit_score"])
                unique_contribution = max(
                    0.0,
                    min(1.0, float(score.get("unique_contribution") or 0.0)),
                )
                overlap_signal = round(1.0 - unique_contribution, 4)
                performance_valid = str(score.get("runtime_status")) == "model_inference"
                change = changes_by_role.get(role, {})
                predecessor_mission_id = None
                quality_delta = None
                marginal_value_delta = None
                leverage_delta = None
                if predecessor is not None:
                    predecessor_mission_id = int(predecessor["mission_id"])
                    quality_delta = round(
                        quality - float(predecessor["quality_score"]), 2
                    )
                    if predecessor["marginal_system_value"] is not None:
                        # Current causal value is still unknown until ablation.
                        marginal_value_delta = None
                    if predecessor["outcome_leverage"] is not None:
                        leverage_delta = None

                conn.execute(
                    """
                    INSERT OR REPLACE INTO worker_longitudinal_metrics (
                        mission_id, agent_role, template_id, template_version,
                        change_id, change_axis, quality_score,
                        heuristic_benefit_score, unique_contribution_score,
                        overlap_signal, execution_time, marginal_system_value,
                        outcome_leverage, predecessor_mission_id, quality_delta,
                        marginal_value_delta, leverage_delta, performance_valid,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(mission_id),
                        role,
                        str(score["template_id"]),
                        str(score["template_version"]),
                        str(change.get("change_id") or "") or None,
                        str(change.get("change_axis") or "") or None,
                        quality,
                        heuristic_benefit,
                        unique_contribution,
                        overlap_signal,
                        float(score["execution_time"]),
                        predecessor_mission_id,
                        quality_delta,
                        marginal_value_delta,
                        leverage_delta,
                        int(performance_valid),
                        created_at,
                    ),
                )
                metric_rows.append(
                    {
                        "role": role,
                        "quality": round(quality, 2),
                        "heuristic_benefit": round(heuristic_benefit, 4),
                        "unique_contribution": round(unique_contribution, 4),
                        "overlap_signal": overlap_signal,
                        "execution_time": round(float(score["execution_time"]), 3),
                        "marginal_system_value": None,
                        "outcome_leverage": None,
                        "predecessor_mission_id": predecessor_mission_id,
                        "quality_delta": quality_delta,
                        "change_id": str(change.get("change_id") or "") or None,
                        "change_axis": str(change.get("change_axis") or "") or None,
                        "performance_valid": performance_valid,
                    }
                )

        return {
            "mission_family": mission_family,
            "comparison_key": comparison_key,
            "experiment_type": experiment_type,
            "performance_valid": experiment_valid,
            "metrics": metric_rows,
        }

    def record_worker_ablation(
        self,
        mission_id: int,
        role: str,
        *,
        full_outcome_score: float,
        ablated_outcome_score: float,
        outcome_leverage: float,
        decision_changed: bool,
        details: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a counterfactual result and promote causal metrics for one worker.

        Scores are normalized 0..1 by the caller's explicit outcome rubric.
        Marginal system value is the signed full-minus-ablated outcome delta; a
        negative value therefore records that the worker harmed the measured result.
        """

        full_score = _finite_unit(full_outcome_score, "full_outcome_score")
        ablated_score = _finite_unit(ablated_outcome_score, "ablated_outcome_score")
        leverage = _finite_unit(outcome_leverage, "outcome_leverage")
        marginal = round(full_score - ablated_score, 4)
        payload = dict(details or {})
        created_at = time.time()

        with self._conn() as conn:
            self._assert_mission_exists(conn, mission_id)
            metric = conn.execute(
                """
                SELECT 1 FROM worker_longitudinal_metrics
                WHERE mission_id = ? AND agent_role = ?
                """,
                (int(mission_id), str(role)),
            ).fetchone()
            if metric is None:
                raise ValueError(
                    f"no longitudinal worker metric for mission={mission_id} role={role}"
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO worker_ablations (
                    mission_id, agent_role, full_outcome_score,
                    ablated_outcome_score, marginal_system_value,
                    outcome_leverage, decision_changed, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(mission_id),
                    str(role),
                    full_score,
                    ablated_score,
                    marginal,
                    leverage,
                    int(bool(decision_changed)),
                    json.dumps(payload, sort_keys=True),
                    created_at,
                ),
            )
            predecessor = conn.execute(
                """
                SELECT previous.marginal_system_value, previous.outcome_leverage
                FROM worker_longitudinal_metrics AS current
                JOIN worker_experiments AS current_experiment
                  ON current_experiment.mission_id = current.mission_id
                JOIN worker_longitudinal_metrics AS previous
                  ON previous.agent_role = current.agent_role
                JOIN worker_experiments AS previous_experiment
                  ON previous_experiment.mission_id = previous.mission_id
                WHERE current.mission_id = ?
                  AND current.agent_role = ?
                  AND previous.mission_id <> current.mission_id
                  AND previous_experiment.mission_family = current_experiment.mission_family
                  AND previous_experiment.comparison_key = current_experiment.comparison_key
                  AND previous.marginal_system_value IS NOT NULL
                  AND previous.outcome_leverage IS NOT NULL
                ORDER BY previous.id DESC
                LIMIT 1
                """,
                (int(mission_id), str(role)),
            ).fetchone()
            marginal_delta = None
            leverage_delta = None
            if predecessor is not None:
                marginal_delta = round(
                    marginal - float(predecessor["marginal_system_value"]), 4
                )
                leverage_delta = round(
                    leverage - float(predecessor["outcome_leverage"]), 4
                )
            conn.execute(
                """
                UPDATE worker_longitudinal_metrics
                SET marginal_system_value = ?, outcome_leverage = ?,
                    marginal_value_delta = ?, leverage_delta = ?
                WHERE mission_id = ? AND agent_role = ?
                """,
                (
                    marginal,
                    leverage,
                    marginal_delta,
                    leverage_delta,
                    int(mission_id),
                    str(role),
                ),
            )

        return {
            "mission_id": int(mission_id),
            "role": str(role),
            "full_outcome_score": round(full_score, 4),
            "ablated_outcome_score": round(ablated_score, 4),
            "marginal_system_value": marginal,
            "outcome_leverage": round(leverage, 4),
            "decision_changed": bool(decision_changed),
            "marginal_value_delta": marginal_delta,
            "leverage_delta": leverage_delta,
        }

    def get_longitudinal_metrics(self, mission_id: int) -> List[Dict[str, Any]]:
        """Return all longitudinal worker measurements for one mission."""

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM worker_longitudinal_metrics
                WHERE mission_id = ?
                ORDER BY id
                """,
                (int(mission_id),),
            ).fetchall()
        return [dict(row) for row in rows]
