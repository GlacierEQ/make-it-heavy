#!/usr/bin/env python3
"""Export a Make-It-Heavy style four-lane plan for Mastermind.

Writes a config compatible with:
  mastermind/config/parallel_coder_tasks.json
"""
import json
import sys
from pathlib import Path

DEFAULT_OUT = Path("outputs/mastermind_parallel_coder_tasks.json")


def build_plan(query):
    return {
        "version": 1,
        "engine": "STEALTH-MICROWAVE",
        "public_role": "Parallel Execution Engine",
        "prime_rule": "Stability is king.",
        "coordinator": {
            "name": "OmniAgent",
            "friendly_alias": "Lil Omni",
            "role": "unified parallel coder coordinator",
            "rule": "route lanes, collect reports, preserve proof"
        },
        "source_query": query,
        "lanes": [
            {
                "id": "research",
                "label": "Research lane",
                "lane": "research",
                "command": ["python", "-c", "print('Research lane ready: gather sources and assumptions')"],
                "expected_artifact": "source_notes",
                "risk": "low"
            },
            {
                "id": "analysis",
                "label": "Analysis lane",
                "lane": "analysis",
                "command": ["python", "-c", "print('Analysis lane ready: compare options and tradeoffs')"],
                "expected_artifact": "analysis_notes",
                "risk": "low"
            },
            {
                "id": "precision_patch",
                "label": "Precision patch lane",
                "lane": "precision_patch",
                "command": ["python", "-c", "print('Patch lane ready: diff plus test plus recovery note required')"],
                "expected_artifact": "patch_plan",
                "risk": "low"
            },
            {
                "id": "verification",
                "label": "Verification lane",
                "lane": "quality",
                "command": ["python", "-c", "print('Verification lane ready: validate outputs before promotion')"],
                "expected_artifact": "verification_report",
                "risk": "low"
            }
        ]
    }


def main():
    query = " ".join(sys.argv[1:]).strip() or "maximize Mastermind parallel coder lanes"
    out = DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = build_plan(query)
    out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "out": str(out), "lanes": len(plan["lanes"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
