# SPDX-License-Identifier: Proprietary
"""Bridge longitudinal worker experiments to externally executed control specimens.

Internal Make-It-Heavy runs naturally link by SQLite mission id.  Real production
experiments may also be executed through an external provider/connector and persisted
as immutable repository receipts.  This module lets a TEMPLATE_DELTA or ABLATION name
exactly one parent lineage form:

* ``parent_mission_id`` for an internal runtime predecessor, or
* ``parent_experiment_ref`` for an immutable ``path@<40-hex-commit>`` receipt.

The external receipt is lineage metadata, not a claim that its contents were ingested
into SQLite.  Matched supervisory comparison against that receipt remains explicit.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Mapping, Optional

from innovation_loop import InnovationConfigurationError
from longitudinal_innovation import (
    EXPERIMENT_TYPES,
    WORKER_EXPERIMENT_BEGIN,
    WORKER_EXPERIMENT_END,
    LongitudinalClaimAwareAdaptiveWorkerLoop,
)
from longitudinal_memory import LongitudinalAdaptiveSwarmMemory


IMMUTABLE_EXPERIMENT_REF_RE = re.compile(
    r"^(?P<path>[^@\s]+)@(?P<revision>[0-9a-fA-F]{40})$"
)
LINEAGE_REQUIRED_TYPES = {"TEMPLATE_DELTA", "ABLATION"}


def _raw_experiment_payload(mission: str) -> Optional[Dict[str, Any]]:
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
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise InnovationConfigurationError(
            f"malformed worker experiment JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise InnovationConfigurationError("worker experiment must be a JSON object")
    return payload


def _mission_with_parent_sentinel(mission: str, payload: Mapping[str, Any]) -> str:
    """Feed the v1 validator a temporary parent id without leaking it to context."""

    patched = dict(payload)
    patched["parent_mission_id"] = 1
    start = mission.find(WORKER_EXPERIMENT_BEGIN)
    end = mission.find(WORKER_EXPERIMENT_END)
    before = mission[: start + len(WORKER_EXPERIMENT_BEGIN)]
    after = mission[end:]
    return f"{before}\n{json.dumps(patched, sort_keys=True)}\n{after}"


class ReceiptLineageClaimAwareAdaptiveWorkerLoop(
    LongitudinalClaimAwareAdaptiveWorkerLoop
):
    """Longitudinal loop that accepts immutable external experiment parents."""

    @staticmethod
    def parse_experiment_context(mission: str) -> Optional[Dict[str, Any]]:
        payload = _raw_experiment_payload(mission)
        if payload is None:
            return None

        experiment_type = str(payload.get("experiment_type") or "").upper().strip()
        if experiment_type and experiment_type not in EXPERIMENT_TYPES:
            # Keep the canonical v1 error surface for unsupported values.
            return LongitudinalClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
                mission
            )

        parent_mission_id = payload.get("parent_mission_id")
        parent_experiment_ref = str(
            payload.get("parent_experiment_ref") or ""
        ).strip() or None
        if parent_mission_id is not None and parent_experiment_ref is not None:
            raise InnovationConfigurationError(
                "worker experiment must use exactly one parent lineage form: "
                "parent_mission_id or parent_experiment_ref"
            )
        if (
            experiment_type in LINEAGE_REQUIRED_TYPES
            and parent_mission_id is None
            and parent_experiment_ref is None
        ):
            raise InnovationConfigurationError(
                f"{experiment_type} experiments require parent_mission_id "
                "or parent_experiment_ref"
            )
        if parent_experiment_ref is not None:
            if IMMUTABLE_EXPERIMENT_REF_RE.fullmatch(parent_experiment_ref) is None:
                raise InnovationConfigurationError(
                    "parent_experiment_ref must be immutable path@<40-hex-commit>"
                )
            validated = LongitudinalClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
                _mission_with_parent_sentinel(mission, payload)
            )
            if validated is None:
                return None
            validated["schema"] = "glaciereq.make-it-heavy.worker-experiment.v2"
            validated["parent_mission_id"] = None
            validated["parent_experiment_ref"] = parent_experiment_ref
            return validated

        validated = LongitudinalClaimAwareAdaptiveWorkerLoop.parse_experiment_context(
            mission
        )
        if validated is not None:
            validated["schema"] = "glaciereq.make-it-heavy.worker-experiment.v2"
            validated["parent_experiment_ref"] = None
        return validated


class ReceiptLineageAdaptiveSwarmMemory(LongitudinalAdaptiveSwarmMemory):
    """Persist immutable external predecessor references beside internal experiments."""

    def _init_db(self) -> None:
        super()._init_db()
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS external_experiment_lineage (
                    mission_id INTEGER PRIMARY KEY,
                    parent_experiment_ref TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_external_experiment_parent
                    ON external_experiment_lineage(parent_experiment_ref);
                """
            )

    def persist_longitudinal_turn(
        self,
        mission_id: int,
        context: Mapping[str, Any],
        scores: list[dict[str, Any]],
        active_roles: list[str],
        report: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = super().persist_longitudinal_turn(
            mission_id,
            context,
            scores,
            active_roles,
            report,
        )
        parent_experiment_ref = str(
            context.get("parent_experiment_ref") or ""
        ).strip() or None
        if parent_experiment_ref is not None:
            if IMMUTABLE_EXPERIMENT_REF_RE.fullmatch(parent_experiment_ref) is None:
                raise ValueError(
                    "parent_experiment_ref must be immutable path@<40-hex-commit>"
                )
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO external_experiment_lineage (
                        mission_id, parent_experiment_ref, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (int(mission_id), parent_experiment_ref, time.time()),
                )
        result["parent_experiment_ref"] = parent_experiment_ref
        return result

    def get_external_parent_ref(self, mission_id: int) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT parent_experiment_ref
                FROM external_experiment_lineage
                WHERE mission_id = ?
                """,
                (int(mission_id),),
            ).fetchone()
        return str(row["parent_experiment_ref"]) if row is not None else None
