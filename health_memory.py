# SPDX-License-Identifier: Proprietary
"""Adaptive memory views that exclude infrastructure failures from learning."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from innovation_memory import AdaptiveSwarmMemory


class HealthAwareAdaptiveSwarmMemory(AdaptiveSwarmMemory):
    """Preserve infrastructure incidents while excluding them from prompt evolution."""

    def get_recent_worker_scores(
        self,
        role: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Return only reviewable model-inference scores for template comparison."""

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT quality_score, benefit_score, runtime_status,
                       template_id, template_version, created_at
                FROM worker_scores
                WHERE agent_role = ? AND runtime_status = 'model_inference'
                ORDER BY id DESC
                LIMIT ?
                """,
                (role, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_worker_portfolio_history(
        self,
        role: str,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Return portfolio-learning rows with worker failures but no shared infra noise.

        Template evolution still consumes only successful model inference through
        :meth:`get_recent_worker_scores`. Portfolio selection needs a wider view:
        role-local timeouts/errors are relevant reliability evidence, while shared
        infrastructure incidents must not become worker-performance penalties.
        The serialized scorecard is rehydrated so richer observational fields remain
        available to the selector without changing the durable worker_scores schema.
        """

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT quality_score, benefit_score, runtime_status,
                       template_id, template_version, scorecard_json, created_at
                FROM worker_scores
                WHERE agent_role = ? AND runtime_status <> 'infra_failure'
                ORDER BY id DESC
                LIMIT ?
                """,
                (role, max(1, int(limit))),
            ).fetchall()

        history: List[Dict[str, Any]] = []
        for row in rows:
            durable = dict(row)
            raw_scorecard = durable.pop("scorecard_json", "")
            scorecard: Dict[str, Any] = {}
            if raw_scorecard:
                try:
                    decoded = json.loads(raw_scorecard)
                except (TypeError, json.JSONDecodeError):
                    decoded = {}
                if isinstance(decoded, dict):
                    scorecard = decoded

            # Durable columns win over serialized duplicates. A failed worker turn is
            # explicitly marked invalid so the portfolio optimizer can penalize it;
            # shared infrastructure rows were excluded in SQL above.
            scorecard.update(durable)
            scorecard["performance_valid"] = (
                str(durable["runtime_status"]) == "model_inference"
            )
            history.append(scorecard)
        return history

    def get_latest_template_adjustments(self) -> Dict[str, Dict[str, Any]]:
        """Return the newest adjustment backed by reviewable model inference only."""

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT adjustment.id, adjustment.agent_role,
                       adjustment.template_id, adjustment.action,
                       adjustment.instruction, adjustment.quality_after,
                       adjustment.benefit_after, adjustment.created_at
                FROM template_adjustments AS adjustment
                WHERE EXISTS (
                    SELECT 1
                    FROM worker_scores AS score
                    WHERE score.mission_id = adjustment.mission_id
                      AND score.agent_role = adjustment.agent_role
                      AND score.runtime_status = 'model_inference'
                )
                ORDER BY adjustment.id DESC
                """
            ).fetchall()

        latest: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            role = str(row["agent_role"])
            if role not in latest:
                latest[role] = dict(row)
        return latest

    def get_adaptive_stats(self) -> Dict[str, Any]:
        """Report evaluated performance separately from infrastructure incidents."""

        with self._conn() as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN runtime_status = 'model_inference' THEN 1 ELSE 0 END)
                        AS evaluated,
                    SUM(CASE WHEN runtime_status = 'infra_failure' THEN 1 ELSE 0 END)
                        AS infrastructure,
                    AVG(CASE WHEN runtime_status = 'model_inference'
                             THEN quality_score END) AS avg_quality,
                    AVG(CASE WHEN runtime_status = 'model_inference'
                             THEN benefit_score END) AS avg_benefit
                FROM worker_scores
                """
            ).fetchone()
            adjustments = conn.execute(
                "SELECT COUNT(*) AS count FROM template_adjustments"
            ).fetchone()["count"]
            topology_adjustments = conn.execute(
                "SELECT COUNT(*) AS count FROM topology_adjustments"
            ).fetchone()["count"]

        return {
            "total_worker_scores": int(totals["total"] or 0),
            "evaluated_worker_scores": int(totals["evaluated"] or 0),
            "infrastructure_worker_scores": int(totals["infrastructure"] or 0),
            "total_template_adjustments": int(adjustments or 0),
            "total_topology_adjustments": int(topology_adjustments or 0),
            "avg_worker_quality": round(float(totals["avg_quality"] or 0.0), 2),
            "avg_worker_benefit": round(float(totals["avg_benefit"] or 0.0), 4),
        }
