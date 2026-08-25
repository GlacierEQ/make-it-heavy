# SPDX-License-Identifier: Proprietary
# Copyright (c) 2026 Casey del Carpio Barton / GlacierEQ — All Rights Reserved
"""
batch.py — Programmatic, resumable entry point for Make-It-Heavy.

The CLI (make_it_heavy.py) is for humans. This module is for scripts and long
runs: it runs a goal through the full pipeline, checkpoints every phase to
RUN_STATE.json, and returns a structured result dict.

Usage:
    python -m make_it_heavy.batch "your goal"
    python -m make_it_heavy.batch --genius "your goal" --source-registry src.json
    python -m make_it_heavy.batch --resume <run-id>
    python -m make_it_heavy.batch --runs            # list saved runs
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from make_it_heavy.genius_orchestration import GeniusOrchestrator, GeniusOrchestrationConfig
from orchestrator import TaskOrchestrator
from make_it_heavy.run_state import RunStateStore, list_runs, PHASE_ORDER

logger = logging.getLogger(__name__)

DEFAULT_RUN_DIR = ".runs"


def _load_source_registry(path: Optional[str]) -> Mapping[str, str]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("source registry must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def _run_swarm_goal(goal: str, config_path: str = "config.yaml") -> str:
    orch = TaskOrchestrator(config_path=config_path, silent=True)
    return orch.orchestrate(goal)


def _run_genius_goal(
    goal: str,
    source_registry: Mapping[str, str],
    config_path: str = "config.yaml",
) -> Dict[str, Any]:
    orch = TaskOrchestrator(config_path=config_path, silent=True)
    cfg = GeniusOrchestrationConfig(goal=goal, source_registry=source_registry)
    engine = GeniusOrchestrator(cfg, orchestrator=orch, config_path=config_path)
    return engine.run_full_orchestration()


def run(
    goal: str,
    *,
    genius: bool = False,
    source_registry: Optional[Mapping[str, str]] = None,
    config_path: str = "config.yaml",
    run_dir: str = DEFAULT_RUN_DIR,
    resume: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a goal with per-phase checkpointing. Resumable."""
    store = RunStateStore(run_dir)

    if resume:
        state = store.load(resume)
        if state is None:
            raise SystemExit(f"No saved run for {resume!r}. Use --runs to list.")
        goal = state.goal
        genius = state.mode == "genius"
        run_id = resume
    else:
        run_id = store.create(goal, mode="genius" if genius else "swarm").run_id
        state = store.load(run_id)

    registry = source_registry if source_registry is not None else {}
    completed = {p["phase"] for p in state.completed_phases}
    result: Dict[str, Any] = {"run_id": run_id, "goal": goal, "mode": state.mode}

    # PHASE 1: decompose
    if "decompose" not in completed:
        orch = TaskOrchestrator(config_path=config_path, silent=True)
        subtasks = orch.decompose_task(goal, orch.num_agents)
        artifact = Path(run_dir) / f"{run_id}.subtasks.json"
        artifact.write_text(json.dumps(subtasks, indent=2), encoding="utf-8")
        store.mark_phase(run_id, "decompose", artifact_path=str(artifact),
                         note=f"{len(subtasks)} subtasks")
        result["subtasks"] = subtasks

    # PHASE 2: swarm (+ firewall + receipts when genius)
    if "swarm" not in completed:
        if genius:
            outcome = _run_genius_goal(goal, registry, config_path=config_path)
        else:
            outcome = _run_swarm_goal(goal, config_path=config_path)
        artifact = Path(run_dir) / f"{run_id}.result.json"
        artifact.write_text(json.dumps(outcome, indent=2, default=str), encoding="utf-8")
        store.mark_phase(run_id, "swarm", artifact_path=str(artifact),
                         note="genius" if genius else "swarm")
        result["outcome"] = outcome

    # PHASE 3: firewall report (genius only; marked N/A otherwise)
    if "firewall" not in completed:
        if genius:
            final = (result.get("outcome") or {}).get("final") or {}
            fw = final.get("firewall") or {}
            artifact = Path(run_dir) / f"{run_id}.firewall.json"
            artifact.write_text(json.dumps(fw, indent=2, default=str), encoding="utf-8")
            store.mark_phase(run_id, "firewall", artifact_path=str(artifact),
                             note=f"pass={fw.get('pass')}")
        else:
            store.mark_phase(run_id, "firewall", note="n/a (swarm mode)")

    # PHASE 4: receipts
    if "receipt" not in completed:
        receipts = ((result.get("outcome") or {}).get("receipts") if genius else []) or []
        artifact = Path(run_dir) / f"{run_id}.receipts.json"
        artifact.write_text(json.dumps(receipts, indent=2, default=str), encoding="utf-8")
        store.mark_phase(run_id, "receipt", artifact_path=str(artifact),
                         note=f"{len(receipts)} receipts")

    # PHASE 5: synthesis summary
    if "synthesis" not in completed:
        synthesis = (
            (result.get("outcome") or {}).get("final", {}).get("result", "")
            if genius else str(result.get("outcome", ""))
        )
        artifact = Path(run_dir) / f"{run_id}.synthesis.md"
        artifact.write_text(synthesis, encoding="utf-8")
        store.mark_phase(run_id, "synthesis", artifact_path=str(artifact))

    state = store.load(run_id)
    result["state"] = state.to_dict()
    result["status"] = state.status
    return result


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Make-It-Heavy batch runner — programmatic, resumable, checkpointed."
    )
    parser.add_argument("goal", nargs="?", default=None, help="goal to run")
    parser.add_argument("--genius", action="store_true",
                        help="route through Genius Orchestration (swarm + semantic firewall + receipts)")
    parser.add_argument("--source-registry", default=None,
                        help="JSON file mapping pointer -> exact source text for the firewall")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR)
    parser.add_argument("--resume", default=None, help="resume a saved run by id")
    parser.add_argument("--runs", action="store_true", help="list saved runs and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.runs:
        for s in list_runs(args.run_dir):
            print(f"{s.run_id}  [{s.mode}]  {s.status:8s}  {s.goal[:60]}")
        return 0

    if not args.goal and not args.resume:
        parser.error("a goal is required unless --resume or --runs is given")

    registry = _load_source_registry(args.source_registry)
    result = run(
        args.goal or "",
        genius=args.genius,
        source_registry=registry,
        config_path=args.config,
        run_dir=args.run_dir,
        resume=args.resume,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "outcome"}, indent=2, default=str))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())