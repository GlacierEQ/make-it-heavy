"""
sequencer.plan — per-repo plan builder.

The plan is the *output* of the sequencer. It is built by scoring every
pattern in the catalog against the repo's profile and selecting the
ones that match. The plan is per-repo unique because the profile is.

The scoring is intentionally transparent: each proposed pattern carries
the profile signals that justified it, so a human reviewer can see
*why* the pattern was proposed, not just *that* it was.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .discover import Profile
from .patterns import Pattern, all_patterns


@dataclass
class ProposedPattern:
    pattern: Pattern
    matched_signals: List[str]
    score: float


@dataclass
class Plan:
    profile: Profile
    proposals: List[ProposedPattern] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "proposals": [
                {
                    "pattern_id": p.pattern.id,
                    "pattern_name": p.pattern.name,
                    "summary": p.pattern.summary,
                    "actions": list(p.pattern.actions),
                    "tests_added": list(p.pattern.tests_added),
                    "matched_signals": p.matched_signals,
                    "score": p.score,
                    "differentiator": p.pattern.differentiator,
                    "est_files_touched": p.pattern.est_files_touched,
                    "est_loc_delta": p.pattern.est_loc_delta,
                }
                for p in self.proposals
            ],
        }


def _match(pattern: Pattern, profile: Profile) -> List[str]:
    """Return the profile signals that this pattern matched on."""
    matched = []
    for sig in pattern.when_profile:
        if profile.has(sig):
            matched.append(sig)
    return matched


def build_plan(profile: Profile, *, record: bool = False) -> Plan:
    """Score every pattern in the catalog against *profile* and return the
    ones whose required signals are all present (in order of priority).

    ``record=False`` (the default) means the plan is read-only: nothing
    is appended to the anti-cookie-cutter history. ``record=True`` means
    the plan was actually accepted for execution and should be compared
    against future runs. Use ``record=True`` only from the ``gate`` CLI
    subcommand, so that exploratory ``discover`` / ``plan`` runs don't
    pollute the history.
    """
    proposals: List[ProposedPattern] = []
    for p in all_patterns():
        matched = _match(p, profile)
        if len(matched) == len(p.when_profile) and p.when_profile:
            score = float(len(matched))
            proposals.append(ProposedPattern(
                pattern=p, matched_signals=matched, score=score,
            ))
    proposals.sort(key=lambda pp: (-pp.score, pp.pattern.id))
    plan = Plan(profile=profile, proposals=proposals)
    if record:
        from .gate import _record_only
        _record_only(plan)
    return plan


def plan_overlap(plan_a: Plan, plan_b: Plan) -> float:
    """Return the Jaccard overlap between two plans' pattern-id sets, in
    [0, 1]. The anti-cookie-cutter gate flags plans that overlap too
    strongly with the most recent previous run."""
    a = {p.pattern.id for p in plan_a.proposals}
    b = {p.pattern.id for p in plan_b.proposals}
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)
