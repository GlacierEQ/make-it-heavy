#!/usr/bin/env python3
"""Validate a Mastermind-compatible lane export.

Default input:
  outputs/mastermind_parallel_coder_tasks.json
"""
import json
import sys
from pathlib import Path

REQUIRED_TOP = ["version", "engine", "public_role", "prime_rule", "coordinator", "lanes"]
REQUIRED_LANE = ["id", "label", "lane", "command", "expected_artifact", "risk"]


def validate(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"missing top-level key: {key}")
    lanes = data.get("lanes", [])
    if len(lanes) != 4:
        errors.append(f"expected 4 lanes, found {len(lanes)}")
    seen = set()
    for lane in lanes:
        lane_id = lane.get("id", "<missing>")
        if lane_id in seen:
            errors.append(f"duplicate lane id: {lane_id}")
        seen.add(lane_id)
        for key in REQUIRED_LANE:
            if key not in lane:
                errors.append(f"{lane_id}: missing {key}")
        command = lane.get("command")
        if not isinstance(command, list) or not command:
            errors.append(f"{lane_id}: command must be a non-empty list")
        if lane.get("risk") not in {"low", "medium", "high"}:
            errors.append(f"{lane_id}: risk must be low, medium, or high")
    if data.get("prime_rule") != "Stability is king.":
        errors.append("prime_rule must be 'Stability is king.'")
    return errors


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs/mastermind_parallel_coder_tasks.json"
    errors = validate(path)
    if errors:
        print("INVALID Mastermind lane export")
        for err in errors:
            print("-", err)
        return 1
    print("VALID Mastermind lane export")
    print(f"Path: {path}")
    print("Lanes: 4")
    print("Prime Rule: Stability is king.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
