# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
run_state.py — Resumable run-state checkpointing for Make-It-Heavy.

Long runs die. This module makes them survivable: every phase writes a
RUN_STATE.json describing what completed and what remains, so a fresh session
(or process) can resume without redoing work.

Schema (v1):
    run_id, goal, mode, created_at, updated_at, status,
    completed_phases: [{phase, finished_at, artifact_path, sha256}],
    next_phase, resume_command, telemetry: {missions, agent_runs, cost_usd}
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN_STATE_SCHEMA = "glaciereq.make-it-heavy.run-state.v1"
PHASE_ORDER = ("decompose", "swarm", "firewall", "receipt", "synthesis")


@dataclass
class PhaseRecord:
    phase: str
    finished_at: float
    artifact_path: Optional[str] = None
    sha256: Optional[str] = None
    note: str = ""


@dataclass
class RunState:
    run_id: str
    goal: str
    mode: str
    created_at: float
    updated_at: float
    status: str
    completed_phases: List[Dict[str, Any]] = field(default_factory=list)
    next_phase: Optional[str] = None
    resume_command: Optional[str] = None
    telemetry: Dict[str, Any] = field(default_factory=dict)
    schema: str = RUN_STATE_SCHEMA

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def is_complete(self) -> bool:
        return self.status == "completed"

    def all_phases_done(self) -> bool:
        done = {p["phase"] for p in self.completed_phases}
        return all(phase in done for phase in PHASE_ORDER)

    def next_to_run(self) -> Optional[str]:
        """Return the next phase that has not completed, or None if done."""
        done = {p["phase"] for p in self.completed_phases}
        for phase in PHASE_ORDER:
            if phase not in done:
                return phase
        return None


def _sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


class RunStateStore:
    """Read/write RUN_STATE.json for a given run directory."""

    def __init__(self, run_dir: str = ".runs"):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        return self.run_dir / f"{run_id}.json"

    def load(self, run_id: str) -> Optional[RunState]:
        p = self.path(run_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return RunState(**{k: v for k, v in data.items() if k in RunState.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CorruptedRunState(f"{p}: {exc}") from exc

    def save(self, state: RunState) -> Path:
        state.updated_at = time.time()
        p = self.path(state.run_id)
        p.write_text(state.to_json(), encoding="utf-8")
        return p

    def mark_phase(
        self,
        run_id: str,
        phase: str,
        artifact_path: Optional[str] = None,
        note: str = "",
    ) -> RunState:
        """Record phase completion. Idempotent: re-marking a phase is a no-op."""
        state = self.load(run_id)
        if state is None:
            raise MissingRunState(f"no run state for {run_id!r}")
        existing = {p["phase"]: p for p in state.completed_phases}
        if phase in existing:
            return state
        state.completed_phases.append(
            asdict(
                PhaseRecord(
                    phase=phase,
                    finished_at=time.time(),
                    artifact_path=artifact_path,
                    sha256=_sha256_file(artifact_path) if artifact_path else None,
                    note=note,
                )
            )
        )
        state.next_phase = state.next_to_run()
        state.status = "completed" if state.all_phases_done() else "running"
        self.save(state)
        return state

    def create(
        self,
        goal: str,
        mode: str = "swarm",
        run_id: Optional[str] = None,
    ) -> RunState:
        rid = run_id or self._default_run_id(goal)
        state = RunState(
            run_id=rid,
            goal=goal,
            mode=mode,
            created_at=time.time(),
            updated_at=time.time(),
            status="running",
            next_phase=PHASE_ORDER[0],
            resume_command=f"python -m make_it_heavy.batch --resume {rid}",
        )
        self.save(state)
        return state

    @staticmethod
    def _default_run_id(goal: str) -> str:
        slug = "".join(c if c.isalnum() else "-" for c in goal.lower()).strip("-")[:48]
        return f"{slug}-{int(time.time())}"


class CorruptedRunState(Exception):
    """Raised when a run-state file cannot be parsed."""


class MissingRunState(Exception):
    """Raised when a referenced run id has no saved state."""


def list_runs(run_dir: str = ".runs") -> List[RunState]:
    store = RunStateStore(run_dir)
    out: List[RunState] = []
    for p in sorted(Path(run_dir).glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(RunState(**{k: v for k, v in data.items() if k in RunState.__dataclass_fields__}))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return out