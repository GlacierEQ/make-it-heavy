"""
sequencer.cli — `python -m make_it_heavy.sequencer <subcommand> <repo>`

Subcommands
-----------
discover <repo>    Print the per-repo profile as JSON.
plan <repo>        Build and print a per-repo plan.
gate <repo>        Build a plan, run the anti-cookie-cutter gate, print verdict.
demo <repo> [<repo> ...]    Discover + plan + gate for each repo, then print
                             a one-line summary per repo so the divergence is
                             easy to see.

Why a CLI? Because the tool has to be runnable from a shell to be useful
to a human reviewer. The JSON output makes it scriptable; the demo
subcommand makes the per-repo divergence obvious at a glance.
"""
from __future__ import annotations

import argparse
import json
import sys

from .discover import build_profile
from .plan import build_plan
from .gate import check as gate_check


def _emit_json(payload, *, indent: int = 2) -> int:
    json.dump(payload, sys.stdout, indent=indent, default=str)
    sys.stdout.write("\n")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    profile = build_profile(args.repo)
    return _emit_json(profile.to_dict())


def cmd_plan(args: argparse.Namespace) -> int:
    profile = build_profile(args.repo)
    plan = build_plan(profile, record=False)
    return _emit_json(plan.to_dict())


def cmd_gate(args: argparse.Namespace) -> int:
    profile = build_profile(args.repo)
    plan = build_plan(profile, record=True)
    verdict = gate_check(plan, threshold=args.threshold)
    payload = {
        "plan": plan.to_dict(),
        "verdict": verdict.to_dict(),
    }
    rc = 0 if verdict.passed else 1
    _emit_json(payload)
    return rc


def cmd_demo(args: argparse.Namespace) -> int:
    lines = []
    for repo in args.repos:
        profile = build_profile(repo)
        plan = build_plan(profile, record=True)
        verdict = gate_check(plan, threshold=args.threshold)
        proposal_ids = [p.pattern.id for p in plan.proposals]
        lines.append({
            "repo": profile.name,
            "signals_count": sum(1 for v in profile.signals.values() if v),
            "proposals": proposal_ids,
            "gate_passed": verdict.passed,
            "overlap_with_previous": round(verdict.overlap_with_previous, 3),
        })
    print("=" * 78)
    print(f"{'repo':<28} {'signals':>8} {'proposals':<42} gate  overlap")
    print("-" * 78)
    for r in lines:
        proposals_str = ", ".join(r["proposals"]) or "(none)"
        if len(proposals_str) > 40:
            proposals_str = proposals_str[:37] + "..."
        gate_mark = "PASS" if r["gate_passed"] else "WARN"
        print(
            f"{r['repo']:<28} {r['signals_count']:>8} {proposals_str:<42} "
            f"{gate_mark}  {r['overlap_with_previous']:.2f}"
        )
    print("=" * 78)
    print(f"across {len(lines)} repos, {len(set(tuple(sorted(r['proposals'])) for r in lines))} unique plan signatures")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m make_it_heavy.sequencer",
        description="Sequencer — per-repo discovery, planning, anti-cookie-cutter gate.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="print a per-repo profile as JSON")
    d.add_argument("repo")
    d.set_defaults(func=cmd_discover)

    pl = sub.add_parser("plan", help="print a per-repo plan as JSON")
    pl.add_argument("repo")
    pl.set_defaults(func=cmd_plan)

    g = sub.add_parser("gate", help="plan + anti-cookie-cutter verdict")
    g.add_argument("repo")
    g.add_argument("--threshold", type=float, default=0.6)
    g.set_defaults(func=cmd_gate)

    demo = sub.add_parser("demo", help="discover+plan+gate across many repos, one row each")
    demo.add_argument("repos", nargs="+")
    demo.add_argument("--threshold", type=float, default=0.6)
    demo.set_defaults(func=cmd_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
