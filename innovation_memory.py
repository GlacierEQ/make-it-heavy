# SPDX-License-Identifier: Proprietary
"""Adaptive score and topology storage layered onto the base swarm memory."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from memory import SwarmMemory


class AdaptiveSwarmMemory(SwarmMemory):
    """Extend SwarmMemory without changing the legacy memory contract."""

    def _init_db(self):
        super()._init_db()
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS worker_scores (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER,
                    worker_id INTEGER,
                    template_id TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    model TEXT,
                    runtime_status TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    benefit_score REAL NOT NULL,
                    execution_time REAL NOT NULL,
                    scorecard_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE TABLE IF NOT EXISTS template_adjustments (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER,
                    agent_role TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    quality_before REAL,
                    quality_after REAL NOT NULL,
                    benefit_before REAL,
                    benefit_after REAL NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE TABLE IF NOT EXISTS topology_adjustments (
                    id INTEGER PRIMARY KEY,
                    mission_id INTEGER,
                    current_worker_count INTEGER NOT NULL,
                    next_worker_count INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_worker_scores_mission
                    ON worker_scores(mission_id);
                CREATE INDEX IF NOT EXISTS idx_worker_scores_role
                    ON worker_scores(agent_role, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_template_adjustments_role
                    ON template_adjustments(agent_role, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_topology_adjustments_mission
                    ON topology_adjustments(mission_id);
                """
            )

    @staticmethod
    def _assert_mission_exists(conn: sqlite3.Connection, mission_id: int) -> None:
        row = conn.execute(
            "SELECT 1 FROM missions WHERE id = ?", (int(mission_id),)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown mission_id: {mission_id}")

    def persist_adaptive_turn(
        self,
        mission_id: int,
        scores: List[Dict[str, Any]],
        adjustments: List[Dict[str, Any]],
        current_worker_count: int,
        next_worker_count: int,
        reason: str,
        report: Dict[str, Any],
    ) -> None:
        """Persist the complete adaptive turn in one transaction."""

        created_at = time.time()
        with self._conn() as conn:
            self._assert_mission_exists(conn, mission_id)
            for scorecard in scores:
                conn.execute(
                    """
                    INSERT INTO worker_scores (
                        mission_id, worker_id, template_id, template_version,
                        agent_role, model, runtime_status, quality_score,
                        benefit_score, execution_time, scorecard_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mission_id, int(scorecard["worker_id"]),
                        scorecard["template_id"], scorecard["template_version"],
                        scorecard["role"], scorecard.get("model", ""),
                        scorecard["runtime_status"],
                        float(scorecard["quality_score"]),
                        float(scorecard["benefit_score"]),
                        float(scorecard["execution_time"]),
                        json.dumps(scorecard, sort_keys=True), created_at,
                    ),
                )
            for adjustment in adjustments:
                conn.execute(
                    """
                    INSERT INTO template_adjustments (
                        mission_id, agent_role, template_id, action, instruction,
                        quality_before, quality_after, benefit_before,
                        benefit_after, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mission_id, adjustment["role"], adjustment["template_id"],
                        adjustment["action"], adjustment["instruction"],
                        adjustment.get("quality_before"),
                        float(adjustment["quality_after"]),
                        adjustment.get("benefit_before"),
                        float(adjustment["benefit_after"]), created_at,
                    ),
                )
            conn.execute(
                """
                INSERT INTO topology_adjustments (
                    mission_id, current_worker_count, next_worker_count,
                    reason, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id, int(current_worker_count), int(next_worker_count),
                    reason, json.dumps(report, sort_keys=True), created_at,
                ),
            )

    def log_worker_score(
        self,
        mission_id: int,
        scorecard: Dict[str, Any],
    ) -> None:
        """Persist one deterministic worker scorecard."""

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO worker_scores (
                    mission_id, worker_id, template_id, template_version,
                    agent_role, model, runtime_status, quality_score,
                    benefit_score, execution_time, scorecard_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    int(scorecard["worker_id"]),
                    scorecard["template_id"],
                    scorecard["template_version"],
                    scorecard["role"],
                    scorecard.get("model", ""),
                    scorecard["runtime_status"],
                    float(scorecard["quality_score"]),
                    float(scorecard["benefit_score"]),
                    float(scorecard["execution_time"]),
                    json.dumps(scorecard, sort_keys=True),
                    time.time(),
                ),
            )

    def log_template_adjustment(
        self,
        mission_id: int,
        adjustment: Dict[str, Any],
    ) -> None:
        """Persist one bounded next-turn template instruction."""

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO template_adjustments (
                    mission_id, agent_role, template_id, action, instruction,
                    quality_before, quality_after, benefit_before,
                    benefit_after, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    adjustment["role"],
                    adjustment["template_id"],
                    adjustment["action"],
                    adjustment["instruction"],
                    adjustment.get("quality_before"),
                    float(adjustment["quality_after"]),
                    adjustment.get("benefit_before"),
                    float(adjustment["benefit_after"]),
                    time.time(),
                ),
            )

    def log_topology_adjustment(
        self,
        mission_id: int,
        current_worker_count: int,
        next_worker_count: int,
        reason: str,
        report: Dict[str, Any],
    ) -> None:
        """Persist the next-turn count and complete worker report."""

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO topology_adjustments (
                    mission_id, current_worker_count, next_worker_count,
                    reason, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mission_id,
                    int(current_worker_count),
                    int(next_worker_count),
                    reason,
                    json.dumps(report, sort_keys=True),
                    time.time(),
                ),
            )

    def get_recent_worker_scores(
        self,
        role: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Return recent scorecards for one role, newest first."""

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT quality_score, benefit_score, runtime_status,
                       template_id, template_version, created_at
                FROM worker_scores
                WHERE agent_role = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (role, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_latest_template_adjustments(self) -> Dict[str, Dict[str, Any]]:
        """Return only the newest adjustment for every role."""

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT adjustment.agent_role, adjustment.template_id,
                       adjustment.action, adjustment.instruction,
                       adjustment.quality_after, adjustment.benefit_after,
                       adjustment.created_at
                FROM template_adjustments AS adjustment
                INNER JOIN (
                    SELECT agent_role, MAX(id) AS max_id
                    FROM template_adjustments
                    GROUP BY agent_role
                ) AS latest
                    ON latest.max_id = adjustment.id
                """
            ).fetchall()
        return {row["agent_role"]: dict(row) for row in rows}

    def get_last_topology_adjustment(self) -> Optional[Dict[str, Any]]:
        """Return the latest count decision and decoded report."""

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT current_worker_count, next_worker_count,
                       reason, report_json, created_at
                FROM topology_adjustments
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["report"] = json.loads(value.pop("report_json"))
        return value

    def get_adaptive_stats(self) -> Dict[str, Any]:
        """Return score and adjustment telemetry for presentation."""

        with self._conn() as conn:
            scores = conn.execute(
                "SELECT COUNT(*) AS count FROM worker_scores"
            ).fetchone()["count"]
            adjustments = conn.execute(
                "SELECT COUNT(*) AS count FROM template_adjustments"
            ).fetchone()["count"]
            topology_adjustments = conn.execute(
                "SELECT COUNT(*) AS count FROM topology_adjustments"
            ).fetchone()["count"]
            average_quality = conn.execute(
                "SELECT AVG(quality_score) AS average FROM worker_scores"
            ).fetchone()["average"] or 0
            average_benefit = conn.execute(
                "SELECT AVG(benefit_score) AS average FROM worker_scores"
            ).fetchone()["average"] or 0
        return {
            "total_worker_scores": scores,
            "total_template_adjustments": adjustments,
            "total_topology_adjustments": topology_adjustments,
            "avg_worker_quality": round(average_quality, 2),
            "avg_worker_benefit": round(average_benefit, 4),
        }
