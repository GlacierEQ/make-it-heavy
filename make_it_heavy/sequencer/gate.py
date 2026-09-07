"""
sequencer.gate — anti-cookie-cutter guard.

The gate's job is to catch templating. A plan is "cookie-cutter" when it
proposes the same patterns as the most recent previous run with high
overlap AND when the matched signals of the proposed patterns are the
same across runs.

The gate keeps a small ring buffer of recent plan digests in
``/root/.sequencer/history.json`` (one entry per repo, last 5). On
every plan build, it computes the Jaccard overlap with the previous
plan for the same repo and flags plans whose overlap exceeds the
threshold AND whose differentiator descriptions are identical.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .plan import Plan, plan_overlap

HISTORY_PATH = Path("/root/.sequencer/history.json")
DEFAULT_THRESHOLD = 0.6  # if overlap > this, the gate warns


@dataclass
class GateVerdict:
    passed: bool
    overlap_with_previous: float
    threshold: float
    reasons: List[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overlap_with_previous": round(self.overlap_with_previous, 3),
            "threshold": self.threshold,
            "reasons": self.reasons,
        }


def _load_history() -> Dict[str, list]:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _save_history(history: Dict[str, list]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def _digest(plan: Plan) -> dict:
    """A small, comparable summary of a plan."""
    return {
        "ts": time.time(),
        "signals": sorted(plan.profile.signals.keys()),
        "proposals": sorted(p.pattern.id for p in plan.proposals),
        "matched_signals": sorted(
            sig for p in plan.proposals for sig in p.matched_signals
        ),
    }


def _record_only(plan: Plan) -> None:
    """Append the plan's digest to the history ring without scoring it.

    Called by :func:`plan.build_plan` when ``record=True`` (i.e. from the
    ``gate`` CLI subcommand). Exploratory ``discover`` / ``plan`` calls
    leave history untouched, so the anti-cookie-cutter gate only
    fires on plans that were actually accepted for execution.
    """
    history = _load_history()
    repo_key = plan.profile.name
    ring = history.get(repo_key, [])
    digest = _digest(plan)
    history[repo_key] = (ring + [digest])[-5:]
    _save_history(history)


def check(plan: Plan, *, threshold: float = DEFAULT_THRESHOLD) -> GateVerdict:
    """Compare *plan* with the most recent recorded plan for the same
    repo and return a verdict. Then append the new digest to the
    history ring (so the next call can compare against this one)."""
    history = _load_history()
    repo_key = plan.profile.name
    ring = history.get(repo_key, [])
    digest = _digest(plan)

    overlap = 0.0
    reasons: List[str] = []
    if ring:
        prev = ring[-1]
        prev_proposals = set(prev.get("proposals", []))
        new_proposals = set(digest["proposals"])
        if prev_proposals or new_proposals:
            overlap = len(prev_proposals & new_proposals) / max(
                1, len(prev_proposals | new_proposals)
            )
        if overlap > threshold:
            reasons.append(
                f"Jaccard overlap with previous plan for {repo_key} is {overlap:.2f} "
                f"(>{threshold:.2f}). The plan looks templated; slow down and "
                "re-check the matched signals."
            )
        prev_matched = set(prev.get("matched_signals", []))
        new_matched = set(digest["matched_signals"])
        if prev_matched == new_matched and len(new_matched) > 0:
            reasons.append(
                f"Identical matched-signals set across the last two runs "
                f"({sorted(new_matched)[:5]}{'...' if len(new_matched) > 5 else ''}). "
                "This is a strong templating smell."
            )

    history[repo_key] = (ring + [digest])[-5:]
    _save_history(history)

    return GateVerdict(
        passed=not reasons,
        overlap_with_previous=overlap,
        threshold=threshold,
        reasons=reasons,
    )
